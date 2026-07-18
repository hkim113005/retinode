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
from engine.eval.overlap import OverlapPolicy
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
    overlap_policy: OverlapPolicy = "reject",
    overlap_eps_um: float = 1.0,
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

    **Tier-agnostic by design.** This primitive does not force FEM: sweeping geometry
    on the diameter-blind analytical tier is legitimate (a fast integration test that
    only exercises the Pareto machinery, or a caller who knows the field is fixed). It
    is a *policy* — "a user comparing diameters wants a tier that can see diameter" —
    that belongs to the caller. Callers making a real geometry comparison should invoke
    :func:`require_geometry_distinguishable` first (as ``api.study_core`` does); it is
    not enforced here so the primitive stays usable on any tier.
    """
    off_target_set = off_target_set or OffTargetSet()
    outcomes: list[GeometryOutcome] = []
    geometry_by_key: dict[str, ArrayGeometry] = {}

    # loop-invariant (depends only on conductivity), so resolve the backend once
    chosen_backend, solve_conductivity = _resolve_backend(conductivity, backend, backend_selector)

    for index, geometry in enumerate(geometries):
        array = build_array(geometry)
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
            overlap_policy=overlap_policy,
            overlap_eps_um=overlap_eps_um,
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
    """Pick the cheapest field tier trustworthy for this conductivity (D2).

    **Conductivity-only, and blind to electrode geometry.** The analytical backend is
    a *point source*: exact for a point in a half-space, but it reads an electrode's
    position and never its extent — two disks of different diameter give a
    byte-identical field (``docs/electrode-geometry.md``; pinned in
    ``tests/field/test_regime.py``). So this function answers "which tier for this
    conductivity", NOT "which tier for this geometry". A sweep that compares geometry
    must use :func:`geometry_field_tier` / :func:`require_geometry_distinguishable`,
    or its frontier is flat by construction (``docs/phase-8-findings.md``).

    - **Homogeneous** → analytical.
    - **Layered, mild contrast** (max σ ratio ≤ ``1 + contrast_tol``) → analytical on
      the homogeneous-σ₁ approximation the P4 S5 regime map shows is trustworthy.
    - **Layered, stronger contrast** → the DOLFINx FEM backend (needs the FEM env).
    """
    if isinstance(conductivity, HomogeneousConductivity):
        return AnalyticalBackend(), conductivity
    if isinstance(conductivity, LayeredConductivity):
        if _layer_contrast(conductivity) <= 1.0 + contrast_tol:
            sigma1 = conductivity.layers[0].sigma_S_per_m
            return AnalyticalBackend(), HomogeneousConductivity(sigma1)
        return FenicsxBackend(), conductivity
    raise TypeError(f"unsupported conductivity model: {type(conductivity).__name__}")


class GeometryTierError(RuntimeError):
    """A geometry comparison was handed a geometry-blind field tier."""


def geometry_field_tier(conductivity: ConductivityModel) -> BackendChoice:
    """The tier for *comparing electrode geometry*: always FEM.

    Only a field solve that resolves the electrode surface (FEM) distinguishes
    diameter or shape — the analytical point source cannot (see
    :func:`resolve_field_tier`). This constructs a ``FenicsxBackend``, which is lazy:
    it imports DOLFINx only when it actually solves, so callers in the uv env can
    build it and hand it across to the FEM env to run.
    """
    return FenicsxBackend(), conductivity


def geometry_varies(geometries: Iterable[ArrayGeometry]) -> bool:
    """Whether these geometries differ in a way the analytical tier cannot see.

    Keyed on **diameter**, the airtight case: diameter never changes an electrode's
    position, so the point-source field is provably identical across it. (Pitch also
    reads as inert on a monopolar-centre protocol, because the moved electrodes carry
    no current — but that is a murkier, protocol-dependent story; diameter is the one
    that is wrong for *any* protocol, so the guard stands on it.)
    """
    return len({round(g.diameter_um, 6) for g in geometries}) > 1


def require_geometry_distinguishable(
    geometries: Iterable[ArrayGeometry], backend: FieldBackend
) -> None:
    """Raise if a geometry-varying sweep would run on a geometry-blind tier.

    Turns the silent-flat-frontier bug (``docs/phase-8-findings.md``) into a loud
    error at the engine boundary: a diameter sweep on the analytical point source
    yields one identical field for every diameter, so the frontier it feeds is
    meaningless. Only fire on the analytical tier — the FEM backends see geometry.
    """
    geoms = list(geometries)
    if isinstance(backend, AnalyticalBackend) and geometry_varies(geoms):
        raise GeometryTierError(
            "this sweep varies electrode diameter, which the analytical tier cannot "
            "see (it is a point source): every diameter would yield the same field "
            "and a flat frontier. Use the FEM tier — engine.study.geometry_field_tier."
        )


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
