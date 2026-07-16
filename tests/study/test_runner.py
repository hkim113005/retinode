"""P5 S3: resumable runner — study status, structured progress, interrupt/resume."""

from __future__ import annotations

import pytest

from engine import spec
from engine.cable.population import PopulationThresholds
from engine.store.project import Project
from engine.study.geometry import ArrayGeometry
from engine.study.geometry_sweep import monopolar_center
from engine.study.runner import (
    GeometryProgress,
    run_geometry_study,
    study_status,
)

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
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        n = len(array.electrodes)
        return PopulationThresholds(patch.target_id, 6.0 + 0.5 * n, {"n1": 6.0 + 3.0 * n})

    return provider


def _run(store, **kw):
    return run_geometry_study(
        GEOMS, PATCH, COND, monopolar_center, store=store, thresholds_provider=_provider(), **kw
    )


def _status(store):
    return study_status(GEOMS, PATCH, COND, monopolar_center, store=store)


# --- study_status: provenance at scale --------------------------------------


def test_study_status_reports_nothing_done_on_a_fresh_store(tmp_path):
    st = _status(Project.open(tmp_path / "fresh"))
    assert st.n_geometries == 3
    assert st.n_complete == 0
    assert st.fraction_done == 0.0
    assert st.remaining_geometries == GEOMS


def test_study_status_reports_everything_done_after_a_full_run(tmp_path):
    store = Project.open(tmp_path / "full")
    _run(store)
    st = _status(store)
    assert st.n_complete == 3
    assert st.fraction_done == 1.0
    assert st.remaining_geometries == []


def test_study_status_matches_the_keys_the_sweep_actually_stored(tmp_path):
    # a partial run (only the first geometry) then status must see exactly it done
    store = Project.open(tmp_path / "partial")
    run_geometry_study(
        GEOMS[:1], PATCH, COND, monopolar_center, store=store, thresholds_provider=_provider()
    )
    st = _status(store)
    assert st.statuses[0].complete
    assert not st.statuses[1].complete
    assert st.n_complete == 1


# --- structured progress ----------------------------------------------------


def test_progress_events_carry_cumulative_and_fraction(tmp_path):
    events: list[GeometryProgress] = []
    _run(Project.open(tmp_path / "prog"), progress=events.append)
    assert [e.index for e in events] == [0, 1, 2]
    assert [e.total for e in events] == [3, 3, 3]
    assert [e.completed for e in events] == [1, 2, 3]
    assert events[-1].fraction == 1.0
    # first run: nothing from cache, everything freshly evaluated
    assert all(not e.from_cache for e in events)
    assert events[-1].n_evaluated_so_far == 3
    assert events[-1].n_cached_so_far == 0


def test_progress_flags_cached_geometries_on_a_re_run(tmp_path):
    store = Project.open(tmp_path / "rerun")
    _run(store)  # populate
    events: list[GeometryProgress] = []
    _run(store, progress=events.append)  # resume: all cached
    assert all(e.from_cache for e in events)
    assert events[-1].n_cached_so_far == 3
    assert events[-1].n_evaluated_so_far == 0


# --- interrupt and resume (the P5 S3 guarantee) -----------------------------


def test_interrupt_mid_study_then_resume_recomputes_nothing_completed(tmp_path):
    store = Project.open(tmp_path / "resume")

    def crash_after_first(p: GeometryProgress) -> None:
        if p.index == 0:
            raise RuntimeError("simulated crash after the first geometry")

    # the run dies after geometry 0 — whose result the sweep already persisted
    with pytest.raises(RuntimeError, match="simulated crash"):
        _run(store, progress=crash_after_first)

    mid = _status(store)
    assert mid.n_complete == 1  # geometry 0 durably stored
    assert not mid.statuses[1].complete and not mid.statuses[2].complete

    # resume: completes the study, serving geometry 0 from the store (no recompute)
    resumed = _run(store)
    assert resumed.n_geometries == 3
    assert resumed.n_cached == 1  # only geometry 0's single result was cached
    assert _status(store).n_complete == 3
