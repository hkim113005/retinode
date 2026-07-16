"""Local parallel execution of a geometry sweep (P5 S4).

Geometries are independent — each builds its own array, solves its own field, and
searches its own thresholds — so they parallelise across CPU cores. Two facts
shape the design:

- **NEURON keeps per-process global state** (the ``h`` interpreter is a
  singleton), so cells for different geometries cannot share a process safely.
  Parallelism must be by *process*, not thread — hence a ``ProcessPoolExecutor``.
- **The on-disk store is not safe for concurrent writes** (HDF5 field cache,
  parquet result index). So workers compute with ``store=None`` and *return* their
  results; the **main process records them serially**. "Content-addressed writes
  keep workers collision-free" then holds trivially: distinct geometries produce
  distinct keys, and only one process ever writes.

Resumability rides the same content-addressed store as the serial path: a geometry
already fully in the store is served from cache and never dispatched. Serial
execution stays the default (``max_workers=1``) and the injectable fallback —
:class:`SerialExecutor` runs jobs in-process, which is also what lets the sweep
*logic* be tested without pickling or NEURON.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from concurrent.futures import Executor, Future, ProcessPoolExecutor
from dataclasses import dataclass
from typing import Any

from engine.eval import EVALUATOR_VERSION, OffTargetSet
from engine.eval.result import EvaluationResult
from engine.eval.safety import DEFAULT_SAFETY_LIMITS, SafetyLimits
from engine.field import FieldBackend
from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig
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
from .runner import GeometryProgress, ProgressCallback
from .sweep import ThresholdsProvider, pareto_selectivity_safety


class SerialExecutor(Executor):
    """An Executor that runs each task inline, in the calling process. The default
    when ``max_workers <= 1`` and the executor to inject in tests: in-process
    execution needs no pickling, so a closure ``thresholds_provider`` works."""

    def submit(self, fn: Any, /, *args: Any, **kwargs: Any) -> Future:
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001 - mirror to the future, re-raised on .result()
            future.set_exception(exc)
        return future


@dataclass(frozen=True)
class _GeometryJob:
    """One geometry's compute, shipped to a worker. All fields must pickle for the
    process pool: ``config_factory`` must be a module-level function (not a lambda)
    and ``thresholds_provider`` must be None or module-level."""

    geometry: ArrayGeometry
    patch: RetinalPatch
    conductivity: ConductivityModel  # already resolved (the solve conductivity)
    backend: FieldBackend
    config_factory: ConfigFactory
    off_target_set: OffTargetSet
    safety_limits: SafetyLimits
    thresholds_provider: ThresholdsProvider | None


def _run_job(job: _GeometryJob) -> GeometryOutcome:
    """Worker entry point: evaluate one geometry with no store (compute only).
    Module-level so it is picklable for the process pool."""
    result = geometry_sweep(
        [job.geometry],
        job.patch,
        job.conductivity,
        job.config_factory,
        backend=job.backend,
        off_target_set=job.off_target_set,
        safety_limits=job.safety_limits,
        thresholds_provider=job.thresholds_provider,
        store=None,
    )
    return result.outcomes[0]


def parallel_geometry_sweep(
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
    thresholds_provider: ThresholdsProvider | None = None,
    max_workers: int | None = None,
    executor: Executor | None = None,
    progress: ProgressCallback | None = None,
) -> GeometrySweepResult:
    """Run a geometry sweep across worker processes. Same result as
    :func:`~engine.study.geometry_sweep.geometry_sweep`, computed in parallel.

    Geometries already complete in ``store`` are served from cache and never
    dispatched (resumable). Pending geometries run in the ``executor`` (default: a
    process pool of ``max_workers`` or ``cpu_count-1``); each worker computes
    without a store and the fresh results are recorded here, in the main process,
    so concurrent store writes never happen. ``progress`` receives one
    :class:`~engine.study.runner.GeometryProgress` per geometry, in geometry order.
    """
    materialized = list(geometries)
    off_target_set = off_target_set or OffTargetSet()

    prepared = [
        _prepare(geom, conductivity, backend, backend_selector, config_factory)
        for geom in materialized
    ]

    cached: dict[int, GeometryOutcome] = {}
    jobs: dict[int, _GeometryJob] = {}
    for i, prep in enumerate(prepared):
        served = _served_from_store(store, prep, patch, off_target_set)
        if served is not None:
            cached[i] = GeometryOutcome(
                prep.geometry,
                prep.array,
                prep.backend.name,
                prep.conductivity,
                tuple(served),
                len(served),
            )
        else:
            jobs[i] = _GeometryJob(
                prep.geometry,
                patch,
                prep.conductivity,
                prep.backend,
                config_factory,
                off_target_set,
                safety_limits,
                thresholds_provider,
            )

    computed = _run_jobs(jobs, max_workers=max_workers, executor=executor)

    # record fresh results serially in the main process (store-safe), then record
    # provenance per (config, result) in config order.
    if store is not None:
        for i, outcome in computed.items():
            prep = prepared[i]
            for config, result in zip(prep.configs, outcome.results, strict=True):
                store.record_run(
                    result,
                    array=prep.array,
                    config=config,
                    patch=patch,
                    off_target_set=off_target_set,
                    conductivity=prep.conductivity,
                    backend_name=prep.backend.name,
                )

    # assemble in geometry order + emit progress + Pareto
    outcomes: list[GeometryOutcome] = []
    geometry_by_key: dict[str, ArrayGeometry] = {}
    cached_acc = evaluated_acc = 0
    for i, prep in enumerate(prepared):
        outcome = cached[i] if i in cached else computed[i]
        outcomes.append(outcome)
        for result in outcome.results:
            geometry_by_key[result.result_key] = prep.geometry
        cached_acc += outcome.n_cached
        evaluated_acc += len(outcome.results) - outcome.n_cached
        if progress is not None:
            progress(
                GeometryProgress(
                    index=i,
                    total=len(materialized),
                    geometry=prep.geometry,
                    outcome=outcome,
                    from_cache=len(outcome.results) > 0
                    and outcome.n_cached == len(outcome.results),
                    n_cached_so_far=cached_acc,
                    n_evaluated_so_far=evaluated_acc,
                )
            )

    pareto = tuple(pareto_selectivity_safety(r for o in outcomes for r in o.results))
    return GeometrySweepResult(tuple(outcomes), pareto, geometry_by_key)


@dataclass(frozen=True)
class _Prepared:
    geometry: ArrayGeometry
    array: ElectrodeArray
    backend: FieldBackend
    conductivity: ConductivityModel
    configs: tuple[StimConfig, ...]


def _prepare(
    geometry: ArrayGeometry,
    conductivity: ConductivityModel,
    backend: FieldBackend | None,
    backend_selector: BackendSelector | None,
    config_factory: ConfigFactory,
) -> _Prepared:
    array = build_array(geometry)
    chosen_backend, solve_conductivity = _resolve_backend(conductivity, backend, backend_selector)
    return _Prepared(
        geometry, array, chosen_backend, solve_conductivity, tuple(config_factory(array))
    )


def _served_from_store(
    store: Project | None, prep: _Prepared, patch: RetinalPatch, off_target_set: OffTargetSet
) -> list[EvaluationResult] | None:
    """The geometry's stored results if *every* config is present (a geometry is
    the unit of caching here), else None -> recompute the whole geometry."""
    if store is None:
        return None
    results: list[EvaluationResult] = []
    for config in prep.configs:
        key = result_key(
            prep.array,
            prep.conductivity,
            config,
            patch,
            off_target_set,
            backend_name=prep.backend.name,
            evaluator_version=EVALUATOR_VERSION,
        )
        result = store.get_result(key)
        if result is None:
            return None
        results.append(result)
    return results


def _run_jobs(
    jobs: dict[int, _GeometryJob], *, max_workers: int | None, executor: Executor | None
) -> dict[int, GeometryOutcome]:
    if not jobs:
        return {}
    own = executor is None
    ex = executor or _make_executor(max_workers)
    try:
        futures = {i: ex.submit(_run_job, job) for i, job in jobs.items()}
        return {i: future.result() for i, future in futures.items()}
    finally:
        if own:
            ex.shutdown()


def _make_executor(max_workers: int | None) -> Executor:
    workers = max_workers if max_workers is not None else max(1, (os.cpu_count() or 1) - 1)
    return SerialExecutor() if workers <= 1 else ProcessPoolExecutor(max_workers=workers)
