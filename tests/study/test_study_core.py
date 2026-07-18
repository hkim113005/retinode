"""P8 S4: the FastAPI-free study orchestration (runs in uv OR the conda FEM env)."""

import pytest

from api.study_core import run_study
from engine.cable.population import PopulationThresholds
from engine.field import AnalyticalBackend
from engine.spec.geometry import radius_um
from engine.study.geometry_sweep import GeometryTierError

_CONTROLS = {
    "diameters_um": [8.0, 12.0, 16.0],
    "pitches_um": [40.0, 60.0],
    "arrangement": "hex",
    "aperture_um": 80.0,
    "neighbor_um": 40.0,
    "sigma_S_per_m": 1.0,
}


def _fake_provider():
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        r = radius_um(array.electrodes[0])
        target = 12.0 - 0.25 * r
        return PopulationThresholds(patch.target_id, target, {"neighbor": target + 3.0})

    return provider


def test_runs_in_process_with_a_fake_provider_and_marks_the_frontier():
    result = run_study(_CONTROLS, thresholds_provider=_fake_provider())
    assert result["n_geometries"] == 6
    pts = result["points"]
    assert len(pts) == 6
    assert all(p["cost_uA"] > 0 for p in pts)
    frontier = [p for p in pts if p["on_frontier"]]
    assert frontier
    for p in frontier:  # every frontier point is genuinely non-dominated
        assert not any(
            q is not p and q["safe"]
            and q["cost_uA"] <= p["cost_uA"] and q["selectivity_uA"] >= p["selectivity_uA"]
            and (q["cost_uA"] < p["cost_uA"] or q["selectivity_uA"] > p["selectivity_uA"])
            for q in pts
        )


def test_reports_progress_monotonically():
    fracs: list[float] = []
    run_study(
        _CONTROLS,
        thresholds_provider=_fake_provider(),
        on_progress=lambda f, _m: fracs.append(f),
    )
    assert fracs == sorted(fracs)
    assert fracs[-1] <= 1.0 and fracs[0] >= 0.0


def test_the_real_field_path_refuses_a_diameter_sweep_on_the_analytical_tier():
    """No provider + analytical backend + varying diameter = the silent-flat bug.
    run_study must raise, not return a degenerate frontier."""
    with pytest.raises(GeometryTierError):
        run_study(_CONTROLS, backend=AnalyticalBackend())  # provider=None -> guard armed


def test_a_fake_provider_bypasses_the_guard():
    """A provider short-circuits the field, so the diameter-blind tier is harmless
    there and the guard must not fire."""
    result = run_study(_CONTROLS, thresholds_provider=_fake_provider(), backend=AnalyticalBackend())
    assert result["n_geometries"] == 6


@pytest.mark.neuron  # run_study's default branch calls _query_reach_um -> place_cell (NEURON)
def test_the_default_real_path_forces_a_floored_fem_backend(monkeypatch):
    """Without an injected provider, run_study must hand the sweep a FEM backend whose
    domain is floored to the cell reach — the two things that prevent a silent flat
    frontier and a point-outside-the-mesh crash. Capture the backend it constructs
    rather than running a real FEM solve."""
    from engine.field import FenicsxBackend

    captured = {}

    class _Stop(Exception):
        pass

    def spy(*_a, backend=None, **_k):
        captured["backend"] = backend
        raise _Stop

    monkeypatch.setattr("api.study_core.geometry_sweep", spy)
    with pytest.raises(_Stop):
        run_study({**_CONTROLS, "diameters_um": [10.0], "pitches_um": [40.0]})

    b = captured["backend"]
    assert isinstance(b, FenicsxBackend)  # FEM, not the diameter-blind analytical tier
    assert b.min_half_width_um > 200.0  # floored to the axon-of-passage reach


@pytest.mark.neuron  # _query_reach_um places the cell (build_active_rgc needs NEURON)
def test_query_reach_covers_the_axon_of_passage():
    """The FEM domain must contain every point the field is sampled at. The reach
    computation is pure and fast, but was only exercised by the conda fem test — a
    regression (min vs max, or forgetting the axon) would sail through the fast and
    NEURON jobs. Pin it: the reach far exceeds the array footprint (the axon runs
    hundreds of µm toward the optic disc)."""
    from api.study_core import _query_reach_um
    from app.scene import build_patch

    reach = _query_reach_um(build_patch(40.0))
    assert reach > 200.0, "the axon of passage should reach well past the electrodes"


def test_min_half_width_floors_the_auto_sized_domain():
    """The floor that keeps those query points inside the mesh — a point outside is a
    hard solve error, not a small inaccuracy (found the hard way running P8 S4 live)."""
    from engine.field.mesh import default_domain
    from engine.spec import HomogeneousConductivity
    from engine.study.geometry import ArrayGeometry, build_array

    array = build_array(ArrayGeometry(10.0, 40.0, "hex", 0.0))  # small: tight default
    cond = HomogeneousConductivity(1.0)
    tight = default_domain(array, cond).half_width_um
    floored = default_domain(array, cond, min_half_width_um=500.0).half_width_um
    assert tight < 500.0  # the array-sized default is small
    assert floored == 500.0  # the floor wins
