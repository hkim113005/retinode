"""P8 S4: the FastAPI-free study orchestration (runs in uv OR the conda FEM env)."""

import math

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
    fracs = []
    run_study(_CONTROLS, thresholds_provider=_fake_provider(), on_progress=lambda f, _m: fracs.append(f))
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


def test_the_default_real_backend_is_fem_not_analytical():
    """Without an injected provider run_study forces FEM — so it never silently uses
    the diameter-blind analytical tier for a geometry comparison."""
    from engine.field import FenicsxBackend
    from engine.study.geometry_sweep import geometry_field_tier

    # the default the real path picks (constructed, not solved — lazy in uv)
    backend, _ = geometry_field_tier(None)
    assert isinstance(backend, FenicsxBackend)
    assert not math.isnan(0.0)  # sanity: this test needs no NEURON, no dolfinx
