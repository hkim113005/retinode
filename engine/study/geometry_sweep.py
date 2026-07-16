"""Geometry sweeps: the outer loop over array geometry (P5 S2).

Phase 2's :func:`engine.study.sweep.sweep` evaluates configurations on a *fixed*
array, solving each cell's field once and reusing it across configs. A geometry
study adds the outer axis: for each :class:`~engine.study.geometry.ArrayGeometry`,
build the array, solve its field once, run a config sub-sweep on it (delegating to
``sweep``), and finally reduce the union of every geometry's results to a
**Pareto frontier** of selectivity vs safety.

Two composition points make different geometries work cleanly:

- **A config factory**, not fixed configs. Configs reference electrode ids, which
  differ between geometries, so the caller passes ``config_factory(array) ->
  configs`` that builds the protocol against the array it is handed (e.g.
  :func:`monopolar_center`).
- **Regime-aware backend choice** (D2). With no explicit backend, the field tier
  is picked per conductivity by :func:`resolve_field_tier`: analytical where it is
  trustworthy (homogeneous, or a mild-contrast layer stack the P4 S5 regime map
  licenses as a homogeneous approximation), FEM where the contrast demands it.

Backend-agnostic and store-backed throughout (resumability rides ``sweep``'s
content-addressed cache), so this stays fast-testable with an injected
``thresholds_provider`` — no NEURON, no FEM.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from engine.eval import OffTargetSet
from engine.eval.result import EvaluationResult
from engine.eval.safety import DEFAULT_SAFETY_LIMITS, SafetyLimits
from engine.field import AnalyticalBackend, FenicsxBackend, FieldBackend
from engine.spec import (
    ConductivityModel,
    ElectrodeArray,
    HomogeneousConductivity,
    LayeredConductivity,
    RetinalPatch,
    StimConfig,
    Waveform,
)

from .geometry import ArrayGeometry, build_array
from .sweep import ThresholdsProvider, pareto_selectivity_safety, sweep

if TYPE_CHECKING:
    from engine.store.project import Project

# Given the array built for one geometry, yield the configs to evaluate on it.
ConfigFactory = Callable[[ElectrodeArray], Iterable[StimConfig]]
# The field tier for a conductivity: the backend and the (possibly simplified)
# conductivity to solve with (a mild layer stack may be approximated homogeneous).
BackendChoice = tuple[FieldBackend, ConductivityModel]
BackendSelector = Callable[[ConductivityModel], BackendChoice]


@dataclass(frozen=True)
class GeometryOutcome:
    """Everything a single geometry produced in the sweep."""

    geometry: ArrayGeometry
    array: ElectrodeArray
    backend_name: str
    conductivity: ConductivityModel  # what was actually solved (may be a homogeneous approx)
    results: tuple[EvaluationResult, ...]
    n_cached: int


@dataclass(frozen=True)
class GeometrySweepResult:
    """The per-geometry outcomes plus the Pareto frontier over every result."""

    outcomes: tuple[GeometryOutcome, ...]
    pareto: tuple[EvaluationResult, ...]
    # result_key -> the geometry that produced it, so a frontier point traces back
    _geometry_by_key: dict[str, ArrayGeometry] = field(compare=False, repr=False)

    @property
    def all_results(self) -> list[EvaluationResult]:
        return [r for o in self.outcomes for r in o.results]

    @property
    def n_geometries(self) -> int:
        return len(self.outcomes)

    @property
    def n_cached(self) -> int:
        return sum(o.n_cached for o in self.outcomes)

    def geometry_of(self, result: EvaluationResult) -> ArrayGeometry:
        """The geometry a result (frontier point) came from."""
        return self._geometry_by_key[result.result_key]

    @property
    def pareto_geometries(self) -> list[ArrayGeometry]:
        """The distinct geometries appearing on the frontier, in frontier order."""
        seen: set[ArrayGeometry] = set()
        ordered: list[ArrayGeometry] = []
        for r in self.pareto:
            g = self.geometry_of(r)
            if g not in seen:
                seen.add(g)
                ordered.append(g)
        return ordered


def geometry_sweep(
    geometries: Iterable[ArrayGeometry],
    patch: RetinalPatch,
    conductivity: ConductivityModel,
    config_factory: ConfigFactory,
    *,
    backend: FieldBackend | None = None,
    backend_selector: BackendSelector | None = None,
    store: Project | None = None,
    off_target_set: OffTargetSet | None = None,
    safety_limits: SafetyLimits = DEFAULT_SAFETY_LIMITS,
    thresholds_provider: ThresholdsProvider | None = None,
    on_geometry: Callable[[int, GeometryOutcome], None] | None = None,
) -> GeometrySweepResult:
    """Sweep ``geometries``: build each array, solve its field once, run the
    ``config_factory`` sub-sweep on it, and reduce all results to a Pareto
    frontier.

    ``backend`` forces one backend for every geometry; otherwise ``backend_selector``
    (or the default :func:`resolve_field_tier`) picks the tier from the
    conductivity. ``store`` makes the whole thing resumable (each geometry's cached
    results are served from disk). ``on_geometry(index, outcome)`` is called after
    each geometry completes (progress).
    """
    off_target_set = off_target_set or OffTargetSet()
    outcomes: list[GeometryOutcome] = []
    geometry_by_key: dict[str, ArrayGeometry] = {}

    for index, geometry in enumerate(geometries):
        array = build_array(geometry)
        chosen_backend, solve_conductivity = _resolve_backend(
            conductivity, backend, backend_selector
        )
        configs = list(config_factory(array))
        sub = sweep(
            array,
            patch,
            solve_conductivity,
            configs,
            store=store,
            off_target_set=off_target_set,
            backend=chosen_backend,
            safety_limits=safety_limits,
            thresholds_provider=thresholds_provider,
        )
        outcome = GeometryOutcome(
            geometry=geometry,
            array=array,
            backend_name=chosen_backend.name,
            conductivity=solve_conductivity,
            results=sub.results,
            n_cached=sub.n_cached,
        )
        outcomes.append(outcome)
        for result in sub.results:
            geometry_by_key[result.result_key] = geometry
        if on_geometry is not None:
            on_geometry(index, outcome)

    pareto = tuple(pareto_selectivity_safety(r for o in outcomes for r in o.results))
    return GeometrySweepResult(tuple(outcomes), pareto, geometry_by_key)


def _resolve_backend(
    conductivity: ConductivityModel,
    backend: FieldBackend | None,
    backend_selector: BackendSelector | None,
) -> BackendChoice:
    if backend is not None:
        return backend, conductivity
    if backend_selector is not None:
        return backend_selector(conductivity)
    return resolve_field_tier(conductivity)


def resolve_field_tier(
    conductivity: ConductivityModel, *, contrast_tol: float = 0.1
) -> BackendChoice:
    """Pick the cheapest field tier that is trustworthy for this conductivity (D2).

    - **Homogeneous** → the analytical backend (exact for a half-space).
    - **Layered, mild contrast** (max σ ratio ≤ ``1 + contrast_tol``) → the
      analytical backend on the homogeneous-σ₁ approximation the P4 S5 regime map
      shows is trustworthy at low contrast.
    - **Layered, stronger contrast** → the DOLFINx FEM backend (needs the FEM env).

    Returns the backend *and* the conductivity to solve with (the mild-contrast
    case substitutes a homogeneous σ₁). Pass an explicit ``backend`` to
    ``geometry_sweep`` to override this entirely.
    """
    if isinstance(conductivity, HomogeneousConductivity):
        return AnalyticalBackend(), conductivity
    if isinstance(conductivity, LayeredConductivity):
        if _layer_contrast(conductivity) <= 1.0 + contrast_tol:
            sigma1 = conductivity.layers[0].sigma_S_per_m
            return AnalyticalBackend(), HomogeneousConductivity(sigma1)
        return FenicsxBackend(), conductivity
    raise TypeError(f"unsupported conductivity model: {type(conductivity).__name__}")


def _layer_contrast(conductivity: LayeredConductivity) -> float:
    """Largest conductivity ratio across layers (≥ 1; 1 == homogeneous)."""
    sigmas = [layer.sigma_S_per_m for layer in conductivity.layers]
    s0 = sigmas[0]
    return max(max(s / s0, s0 / s) for s in sigmas)


def monopolar_center(
    array: ElectrodeArray,
    *,
    amplitude_scale_uA: float = 1.0,
    phase_width_us: float = 200.0,
    distant_return: bool = True,
) -> list[StimConfig]:
    """A one-config protocol: drive the electrode nearest the array centre,
    cathodic-first, with a distant return. A sensible default ``config_factory``
    for a geometry sweep — usable directly, or wrap it to tune the waveform."""
    center = min(array.electrodes, key=lambda e: math.hypot(e.pos_um[0], e.pos_um[1]))
    return [
        StimConfig.from_map(
            {center.id: -1.0},
            waveform=Waveform(phase_width_us=phase_width_us, amplitude_scale_uA=amplitude_scale_uA),
            distant_return=distant_return,
        )
    ]
