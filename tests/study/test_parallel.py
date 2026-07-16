"""P5 S4: local parallel geometry sweep.

Fast tests drive the orchestration with an in-process SerialExecutor (no pickling,
no NEURON); one neuron-marked test runs a real sweep across worker processes."""

from __future__ import annotations

import pytest

from engine import spec
from engine.cable.population import PopulationThresholds
from engine.store.project import Project
from engine.study.geometry import ArrayGeometry
from engine.study.geometry_sweep import geometry_sweep, monopolar_center
from engine.study.parallel import SerialExecutor, parallel_geometry_sweep

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
PATCH = spec.RetinalPatch(
    cells=(
        spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
        spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
    ),
    target_id="t",
    optic_disc_um=(2000.0, 0.0, -20.0),
)
GEOMS = [
    ArrayGeometry(10.0, 30.0, "grid", 30.0),
    ArrayGeometry(10.0, 30.0, "grid", 60.0),
    ArrayGeometry(10.0, 30.0, "hex", 60.0),
]


def _provider():
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None):
        n = len(array.electrodes)
        return PopulationThresholds(patch.target_id, 6.0 + 0.5 * n, {"n1": 6.0 + 3.0 * n})

    return provider


def _parallel(**kw):
    return parallel_geometry_sweep(
        GEOMS,
        PATCH,
        COND,
        monopolar_center,
        thresholds_provider=_provider(),
        executor=SerialExecutor(),
        **kw,
    )


def test_parallel_matches_serial_results_and_frontier():
    prov = _provider()
    serial = geometry_sweep(GEOMS, PATCH, COND, monopolar_center, thresholds_provider=prov)
    par = parallel_geometry_sweep(
        GEOMS, PATCH, COND, monopolar_center, thresholds_provider=prov, executor=SerialExecutor()
    )
    assert par.n_geometries == serial.n_geometries == 3
    assert {r.result_key for r in par.all_results} == {r.result_key for r in serial.all_results}
    assert set(par.pareto_geometries) == set(serial.pareto_geometries)


def test_progress_fires_per_geometry_in_order():
    events: list[int] = []
    _parallel(progress=lambda e: events.append(e.index))
    assert events == [0, 1, 2]


def test_store_makes_a_re_run_fully_cached_and_dispatches_nothing(tmp_path):
    store = Project.open(tmp_path / "par")
    first = _parallel(store=store)
    assert first.n_cached == 0

    # second run: every geometry is served from the store, no job is dispatched.
    # a poisoned executor proves nothing runs (submit would raise if called).
    class _Poison(SerialExecutor):
        def submit(self, fn, /, *args, **kwargs):  # type: ignore[override]
            raise AssertionError("no geometry should be dispatched on a fully-cached re-run")

    second = parallel_geometry_sweep(
        GEOMS,
        PATCH,
        COND,
        monopolar_center,
        store=store,
        thresholds_provider=_provider(),
        executor=_Poison(),
    )
    assert second.n_cached == len(second.all_results)


def test_max_workers_one_runs_serially_without_processes():
    res = parallel_geometry_sweep(
        GEOMS, PATCH, COND, monopolar_center, thresholds_provider=_provider(), max_workers=1
    )
    assert res.n_geometries == 3
    assert len(res.pareto) >= 1


def test_serial_executor_captures_and_reraises_exceptions():
    fut = SerialExecutor().submit(lambda: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        fut.result()


# --- real parallelism across processes (pickling + NEURON) -------------------

_E2E_PATCH = spec.RetinalPatch(
    cells=(
        spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
        spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
        spec.RGC(id="far", cell_type="parasol_on", soma_um=(500.0, 0.0, -20.0)),
    ),
    target_id="t",
    optic_disc_um=(2000.0, 0.0, -20.0),
)
_E2E_GEOMS = [
    ArrayGeometry(8.0, 40.0, "grid", 0.0),
    ArrayGeometry(16.0, 40.0, "grid", 0.0),
]


@pytest.mark.neuron
@pytest.mark.slow
def test_real_parallel_sweep_across_worker_processes(neuron_h, tmp_path):
    store = Project.open(tmp_path / "par")
    res = parallel_geometry_sweep(
        _E2E_GEOMS, _E2E_PATCH, COND, monopolar_center, store=store, max_workers=2
    )
    assert res.n_geometries == 2
    assert all(r.activated for r in res.all_results)  # real threshold searches, in workers

    # resumable: the second run serves both geometries from the store, no worker
    again = parallel_geometry_sweep(
        _E2E_GEOMS, _E2E_PATCH, COND, monopolar_center, store=store, max_workers=2
    )
    assert again.n_cached == len(again.all_results)
