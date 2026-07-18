"""Configuration sweeps on a fixed array: the cheap, Tier-1 half of §9.

Because the array (geometry) is fixed, every configuration reuses one transfer
matrix per cell (P2 S1): the population is placed and solved *once*, and each
configuration is then just a threshold search over the already-solved field. The
sweep caches through a project store (P2 S2) — a configuration whose ``result_key``
is already present is served from disk, no re-solve — and records provenance for
every fresh evaluation (P2 S3). What comes back is the collected results plus
helpers to rank them into a shortlist.

Geometry sweeps (a new field per array) and parallel/cluster execution are Phase
5; this stays synchronous and single-array.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.cable.morphology import RGCModel
from engine.cable.multisite import multisite_threshold
from engine.cable.placement import place_cell
from engine.cable.population import PopulationThresholds, severed_segments
from engine.cable.solved import SolvedField, solve_field
from engine.eval import EVALUATOR_VERSION, OffTargetSet, evaluate
from engine.eval.offtarget import select_off_targets
from engine.eval.overlap import OverlapConflict, OverlapPolicy
from engine.eval.result import EvaluationResult
from engine.eval.safety import DEFAULT_SAFETY_LIMITS, SafetyLimits
from engine.field import AnalyticalBackend, FieldBackend, backend_solve_params
from engine.spec import (
    ConductivityModel,
    ElectrodeArray,
    RetinalPatch,
    StimConfig,
    Waveform,
)
from engine.store.keys import result_key

if TYPE_CHECKING:
    from engine.store.project import Project

# A thresholds provider matches engine.eval's ThresholdsProvider protocol.
ThresholdsProvider = Callable[..., PopulationThresholds]


# --- configuration generators (pure) ----------------------------------------


def waveform_shape_sweep(
    weights: dict[str, float],
    phase_widths_us: Iterable[float],
    *,
    distant_return: bool = True,
    amplitude_scale_uA: float = 1.0,
) -> list[StimConfig]:
    """Configs that vary the waveform (phase width) over one fixed weight pattern."""
    return [
        StimConfig.from_map(
            dict(weights),
            waveform=Waveform(phase_width_us=pw, amplitude_scale_uA=amplitude_scale_uA),
            distant_return=distant_return,
        )
        for pw in phase_widths_us
    ]


def steering_sweep(
    weight_maps: Iterable[dict[str, float]],
    *,
    phase_width_us: float = 200.0,
    distant_return: bool = True,
) -> list[StimConfig]:
    """Configs that steer the current pattern (one per weight map) over one waveform."""
    return [
        StimConfig.from_map(
            dict(wm),
            waveform=Waveform(phase_width_us=phase_width_us),
            distant_return=distant_return,
        )
        for wm in weight_maps
    ]


# --- the sweep --------------------------------------------------------------


@dataclass(frozen=True)
class SweepResult:
    results: tuple[EvaluationResult, ...]
    n_cached: int  # served from the store without re-solving

    @property
    def n_evaluated(self) -> int:
        return len(self.results) - self.n_cached


class SolvedPopulation:
    """Places the target + off-targets once and solves each field once, so a whole
    sweep of configurations reuses the transfer matrices (the P2 S1 payoff).

    Public because the amplitude sweep (``engine.study.activation``) needs exactly
    this placement — including the overlap severing — and a second copy of that logic
    is how the two would drift apart on the question of where the metal is.

    It lives here rather than in ``engine.cable.population`` (its more natural home)
    because it needs ``select_off_targets`` from ``engine.eval``, and ``engine.eval``
    already imports ``cable.population`` — moving it down would close an import
    cycle. ``study`` sits above both, so it is the honest place for it.
    """

    def __init__(
        self,
        patch: RetinalPatch,
        array: ElectrodeArray,
        conductivity: ConductivityModel,
        off_target_set: OffTargetSet,
        backend: FieldBackend,
        *,
        overlap_eps_um: float = 1.0,
    ) -> None:
        self._array = array
        self._conductivity = conductivity
        self._has_body = any(e.body is not None for e in array.electrodes)

        def solve(cell):  # sever any in-metal compartments before the (reused) solve
            sev = (
                severed_segments(cell, array, eps_um=overlap_eps_um)
                if self._has_body
                else frozenset()
            )
            return solve_field(cell, array, conductivity, backend, deactivated=sev), sev

        self._target = place_cell(patch.target(), optic_disc=patch.optic_disc_um)
        self._target_solved, self._target_severed = solve(self._target)
        self._target_id = patch.target().id
        self._offs = [
            (rgc.id, cell, *solve(cell))
            for rgc in select_off_targets(patch, array, off_target_set)
            for cell in (place_cell(rgc, optic_disc=patch.optic_disc_um),)
        ]

    def cells(self) -> list[tuple[str, bool, RGCModel, SolvedField, frozenset[int]]]:
        """``(id, is_target, model, solved_field, severed)`` for the whole placed
        population, target first — so a caller can drive each cell at an amplitude of
        its choosing against the field that was already solved for it."""
        return [
            (self._target_id, True, self._target, self._target_solved, self._target_severed),
            *((cid, False, cell, solved, sev) for cid, cell, solved, sev in self._offs),
        ]

    def thresholds(
        self,
        patch: RetinalPatch,
        array: ElectrodeArray,
        config: StimConfig,
        conductivity: ConductivityModel,
        *,
        off_target_set: OffTargetSet | None = None,
        backend: FieldBackend | None = None,
        overlap_policy: OverlapPolicy = "reject",
        overlap_eps_um: float = 1.0,
    ) -> PopulationThresholds:
        if overlap_policy == "reject" and self._target_severed:
            raise OverlapConflict(
                f"cell {self._target_id!r} has {len(self._target_severed)} compartment(s) "
                f"inside an electrode body; use the 'displace' overlap policy or move the cell"
            )
        target_thr = multisite_threshold(
            self._target, self._array, config, self._conductivity,
            solved=self._target_solved, deactivated=self._target_severed,
        ).threshold_uA
        off: dict[str, float] = {}
        for cid, cell, solved, severed in self._offs:
            if overlap_policy == "reject" and severed:
                raise OverlapConflict(
                    f"cell {cid!r} has {len(severed)} compartment(s) inside an electrode "
                    f"body; use the 'displace' overlap policy or move the cell"
                )
            thr = multisite_threshold(
                cell, self._array, config, self._conductivity,
                solved=solved, deactivated=severed,
            ).threshold_uA
            if thr is not None:
                off[cid] = thr
        return PopulationThresholds(patch.target_id, target_thr, off)


def sweep(
    array: ElectrodeArray,
    patch: RetinalPatch,
    conductivity: ConductivityModel,
    configs: Iterable[StimConfig],
    *,
    store: Project | None = None,
    off_target_set: OffTargetSet | None = None,
    backend: FieldBackend | None = None,
    safety_limits: SafetyLimits = DEFAULT_SAFETY_LIMITS,
    overlap_policy: OverlapPolicy = "reject",
    overlap_eps_um: float = 1.0,
    thresholds_provider: ThresholdsProvider | None = None,
) -> SweepResult:
    """Evaluate each configuration over a fixed array, reusing fields and the cache.

    ``store`` (a Project) makes it content-addressed: a config whose ``result_key``
    is present is served from disk; a fresh one is evaluated and its result +
    provenance recorded. The population is placed and solved lazily on the first
    cache miss, so an all-cached re-run does no NEURON work. ``thresholds_provider``
    overrides the field solve (used in fast tests to skip NEURON).
    """
    off_target_set = off_target_set or OffTargetSet()
    backend = backend or AnalyticalBackend()

    results: list[EvaluationResult] = []
    n_cached = 0
    solved_pop: SolvedPopulation | None = None

    for config in configs:
        rkey = result_key(
            array,
            conductivity,
            config,
            patch,
            off_target_set,
            backend_name=backend.name,
            evaluator_version=EVALUATOR_VERSION,
            solve_params=backend_solve_params(backend, array, conductivity),
        )
        if store is not None:
            cached = store.get_result(rkey)  # None means a miss to evaluate
            if cached is not None:
                results.append(cached)
                n_cached += 1
                continue

        provider = thresholds_provider
        if provider is None:
            if solved_pop is None:  # lazy: place + solve once, on the first miss
                solved_pop = SolvedPopulation(
                    patch, array, conductivity, off_target_set, backend,
                    overlap_eps_um=overlap_eps_um,
                )
            provider = solved_pop.thresholds

        result = evaluate(
            patch,
            array,
            config,
            conductivity,
            off_target_set=off_target_set,
            safety_limits=safety_limits,
            backend=backend,
            overlap_policy=overlap_policy,
            overlap_eps_um=overlap_eps_um,
            thresholds_provider=provider,
        )
        if store is not None:
            store.record_run(
                result,
                array=array,
                config=config,
                patch=patch,
                off_target_set=off_target_set,
                conductivity=conductivity,
                backend_name=backend.name,
            )
        results.append(result)

    return SweepResult(results=tuple(results), n_cached=n_cached)


# --- ranking a shortlist ----------------------------------------------------


def rank_by_window(results: Iterable[EvaluationResult]) -> list[EvaluationResult]:
    """Best-first: usable windows before unusable, then by margin, then selectivity."""

    def key(r: EvaluationResult) -> tuple[int, float, float]:
        w = r.window
        if w is None or not w.is_usable:
            return (0, float("-inf"), float("-inf"))
        return (1, w.usable_margin_uA, r.sow.ratio if r.sow else 0.0)

    return sorted(results, key=key, reverse=True)


def _dominates(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    """a dominates b when it is >= on every objective and > on at least one."""
    return all(x >= y for x, y in zip(a, b, strict=True)) and any(
        x > y for x, y in zip(a, b, strict=True)
    )


def pareto_front(
    results: Iterable[EvaluationResult],
    objectives: list[Callable[[EvaluationResult], float]],
) -> list[EvaluationResult]:
    """The non-dominated results over ``objectives`` (each maximized)."""
    scored = [(r, tuple(f(r) for f in objectives)) for r in results]
    return [r for r, v in scored if not any(_dominates(ov, v) for o, ov in scored if o is not r)]


def pareto_selectivity_safety(results: Iterable[EvaluationResult]) -> list[EvaluationResult]:
    """Pareto frontier trading selectivity (SOW ratio) against safety headroom
    (how many times the target threshold the safety ceiling allows)."""
    usable = [
        r for r in results if r.window is not None and r.window.is_usable and r.sow is not None
    ]

    def selectivity(r: EvaluationResult) -> float:
        return r.sow.ratio if r.sow else 0.0

    def safety_headroom(r: EvaluationResult) -> float:
        w = r.window
        return w.safety_ceiling_uA / w.target_uA if w else 0.0

    return pareto_front(usable, [selectivity, safety_headroom])
