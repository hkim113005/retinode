"""Resumable geometry-study runner: progress + provenance at scale (P5 S3).

The geometry sweep is already store-backed and content-addressed (P5 S2): each
result is written to the ``Project`` the moment it is evaluated, so an interrupted
run leaves every completed geometry durably on disk and a re-run recomputes none
of it. This module adds the two things that turn that substrate into a study you
can run unattended and resume without bookkeeping:

- :func:`study_status` — ask a store *how far along a study is* without computing
  anything: it recomputes each geometry's result keys and checks membership, so
  you can report progress before a run, or plan a resume ("3 of 10 done, these 7
  remain"). This is the provenance-at-scale query.
- :func:`run_geometry_study` — the same run as :func:`~engine.study.geometry_sweep.geometry_sweep`,
  but emitting a structured :class:`GeometryProgress` per geometry (cumulative
  cached vs evaluated, ``from_cache``, fraction done) suitable for a progress bar
  or a long log. Resuming is just calling it again against the same store.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from engine.eval import EVALUATOR_VERSION, OffTargetSet
from engine.eval.overlap import OverlapPolicy
from engine.eval.safety import DEFAULT_SAFETY_LIMITS, SafetyLimits
from engine.field import FieldBackend, backend_solve_params
from engine.spec import ConductivityModel, RetinalPatch
from engine.store.keys import result_key
from engine.store.project import Project

from .geometry import ArrayGeometry, build_array
from .geometry_sweep import (
    BackendSelector,
    ConfigFactory,
    GeometryOutcome,
    GeometrySweepResult,
    _resolve_backend,
    geometry_sweep,
)
from .sweep import ThresholdsProvider

# --- provenance at scale: how much of a study is already done? --------------


@dataclass(frozen=True)
class GeometryStatus:
    """How many of one geometry's configs already have a stored result."""

    geometry: ArrayGeometry
    total: int  # configs the factory produces for this geometry
    completed: int  # of those, how many are already in the store

    @property
    def complete(self) -> bool:
        return self.total > 0 and self.completed == self.total


@dataclass(frozen=True)
class StudyStatus:
    """A study's completion, read from the store without computing anything."""

    statuses: tuple[GeometryStatus, ...]

    @property
    def n_geometries(self) -> int:
        return len(self.statuses)

    @property
    def n_complete(self) -> int:
        return sum(1 for s in self.statuses if s.complete)

    @property
    def n_results_total(self) -> int:
        return sum(s.total for s in self.statuses)

    @property
    def n_results_done(self) -> int:
        return sum(s.completed for s in self.statuses)

    @property
    def fraction_done(self) -> float:
        total = self.n_results_total
        return self.n_results_done / total if total else 1.0

    @property
    def remaining_geometries(self) -> list[ArrayGeometry]:
        """Geometries not yet fully in the store — what a resume still has to do."""
        return [s.geometry for s in self.statuses if not s.complete]


def study_status(
    geometries: Iterable[ArrayGeometry],
    patch: RetinalPatch,
    conductivity: ConductivityModel,
    config_factory: ConfigFactory,
    *,
    store: Project,
    off_target_set: OffTargetSet | None = None,
    backend: FieldBackend | None = None,
    backend_selector: BackendSelector | None = None,
    evaluator_version: str = EVALUATOR_VERSION,
) -> StudyStatus:
    """How much of this geometry study is already in ``store`` — no field solve,
    no threshold search, just the same ``result_key`` the sweep would compute,
    checked for membership. Use the same arguments you would pass to the sweep so
    the keys line up exactly."""
    off_target_set = off_target_set or OffTargetSet()
    statuses: list[GeometryStatus] = []
    for geometry in geometries:
        array = build_array(geometry)
        chosen_backend, solve_conductivity = _resolve_backend(
            conductivity, backend, backend_selector
        )
        configs = list(config_factory(array))
        done = sum(
            store.has_result(
                result_key(
                    array,
                    solve_conductivity,
                    config,
                    patch,
                    off_target_set,
                    backend_name=chosen_backend.name,
                    evaluator_version=evaluator_version,
                    solve_params=backend_solve_params(chosen_backend, array, solve_conductivity),
                )
            )
            for config in configs
        )
        statuses.append(GeometryStatus(geometry, len(configs), done))
    return StudyStatus(tuple(statuses))


# --- the resumable run, with structured progress ----------------------------


@dataclass(frozen=True)
class GeometryProgress:
    """One geometry's completion event, emitted as a run proceeds."""

    index: int  # 0-based geometry index
    total: int  # geometries in this run
    geometry: ArrayGeometry
    outcome: GeometryOutcome
    from_cache: bool  # this geometry was served entirely from the store (no recompute)
    n_cached_so_far: int  # cumulative results served from the store
    n_evaluated_so_far: int  # cumulative results freshly evaluated

    @property
    def completed(self) -> int:
        """Geometries finished so far (1-based)."""
        return self.index + 1

    @property
    def fraction(self) -> float:
        return self.completed / self.total if self.total else 1.0


ProgressCallback = Callable[[GeometryProgress], None]


def run_geometry_study(
    geometries: Iterable[ArrayGeometry],
    patch: RetinalPatch,
    conductivity: ConductivityModel,
    config_factory: ConfigFactory,
    *,
    store: Project | None = None,
    backend: FieldBackend | None = None,
    backend_selector: BackendSelector | None = None,
    off_target_set: OffTargetSet | None = None,
    safety_limits: SafetyLimits = DEFAULT_SAFETY_LIMITS,
    overlap_policy: OverlapPolicy = "reject",
    overlap_eps_um: float = 1.0,
    thresholds_provider: ThresholdsProvider | None = None,
    progress: ProgressCallback | None = None,
) -> GeometrySweepResult:
    """Run (or resume) a geometry study, emitting a structured
    :class:`GeometryProgress` after each geometry. Same results as
    :func:`~engine.study.geometry_sweep.geometry_sweep`; the value added is the
    cumulative progress (cached vs evaluated, fraction done) and, because it is
    store-backed, that re-invoking it against the same store resumes with no
    recomputation of completed geometries."""
    materialized = list(geometries)
    total = len(materialized)
    cached_acc = 0
    evaluated_acc = 0

    def _on(index: int, outcome: GeometryOutcome) -> None:
        nonlocal cached_acc, evaluated_acc
        cached_acc += outcome.n_cached
        evaluated_acc += len(outcome.results) - outcome.n_cached
        if progress is not None:
            progress(
                GeometryProgress(
                    index=index,
                    total=total,
                    geometry=outcome.geometry,
                    outcome=outcome,
                    from_cache=len(outcome.results) > 0
                    and outcome.n_cached == len(outcome.results),
                    n_cached_so_far=cached_acc,
                    n_evaluated_so_far=evaluated_acc,
                )
            )

    return geometry_sweep(
        materialized,
        patch,
        conductivity,
        config_factory,
        backend=backend,
        backend_selector=backend_selector,
        store=store,
        off_target_set=off_target_set,
        safety_limits=safety_limits,
        overlap_policy=overlap_policy,
        overlap_eps_um=overlap_eps_um,
        thresholds_provider=thresholds_provider,
        on_geometry=_on,
    )
