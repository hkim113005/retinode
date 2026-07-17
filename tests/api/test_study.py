"""P7 S4: the geometry sweep runs as a job and returns a Pareto frontier."""

import math
import time

import pytest
from fastapi.testclient import TestClient

from api import create_app
from engine.cable.population import PopulationThresholds
from engine.spec.geometry import radius_um

_STUDY = {
    "diameters_um": [8.0, 12.0, 16.0],
    "pitches_um": [40.0, 60.0],
    "arrangement": "hex",
    "aperture_um": 80.0,
    "neighbor_um": 40.0,
    "sigma_S_per_m": 1.0,
}


def _geometry_varying_provider():
    """A fast fake whose target threshold shrinks with electrode size and whose
    off-target rises with the array's spread — so the sweep has a real trade-off."""

    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        r = radius_um(array.electrodes[0])
        spread = max((math.hypot(*e.pos_um[:2]) for e in array.electrodes), default=0.0)
        target = 12.0 - 0.25 * r  # bigger disk -> lower threshold
        off = target + 3.0 + 0.05 * spread  # wider array -> more selective
        return PopulationThresholds(patch.target_id, target, {"neighbor": off})

    return provider


def _poll(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    body = client.get(f"/jobs/{job_id}").json()
    while body["status"] == "running" and time.time() < deadline:
        time.sleep(0.03)
        body = client.get(f"/jobs/{job_id}").json()
    return body


def test_study_sweeps_geometries_to_a_frontier():
    client = TestClient(create_app(thresholds_provider=_geometry_varying_provider()))
    submitted = client.post("/study", json=_STUDY).json()
    body = _poll(client, submitted["id"])
    assert body["status"] == "done"
    study = body["study"]
    # 3 diameters x 2 pitches = 6, minus (d16,p<16 has none here) -> all 6 valid
    assert study["n_geometries"] == 6
    pts = study["points"]
    assert len(pts) == 6
    assert all(p["cost_uA"] > 0 and p["selectivity_uA"] > 0 for p in pts)
    # a non-empty frontier, and every frontier point is genuinely non-dominated
    frontier = [p for p in pts if p["on_frontier"]]
    assert frontier
    for p in frontier:
        assert not any(
            q is not p
            and q["safe"]
            and q["cost_uA"] <= p["cost_uA"]
            and q["selectivity_uA"] >= p["selectivity_uA"]
            and (q["cost_uA"] < p["cost_uA"] or q["selectivity_uA"] > p["selectivity_uA"])
            for q in pts
        )


def test_study_drops_overlapping_combos():
    client = TestClient(create_app(thresholds_provider=_geometry_varying_provider()))
    body = _poll(
        client,
        client.post(
            "/study", json={**_STUDY, "diameters_um": [20.0], "pitches_um": [10.0, 30.0]}
        ).json()["id"],
    )
    # pitch 10 < diameter 20 is dropped; only (20, 30) survives
    assert body["study"]["n_geometries"] == 1


def test_no_provider_dispatches_the_study_to_the_fem_env(monkeypatch):
    """Comparing geometry is FEM-only, so a production study (no injected provider)
    dispatches the whole sweep to the conda env rather than running analytical."""
    seen = {}

    def fake_dispatch(controls, report, **_):
        from api.models import StudyPoint, StudyResult

        seen["diameters"] = controls.diameters_um
        report(0.5, "solving geometry 1 of 1")
        return StudyResult(
            points=[
                StudyPoint(
                    diameter_um=10.0, pitch_um=50.0, cost_uA=8.0,
                    selectivity_uA=4.0, safe=True, on_frontier=True,
                )
            ],
            n_geometries=1,
        )

    monkeypatch.setattr("api.routes.study.run_study_job", fake_dispatch)
    client = TestClient(create_app())  # NO provider -> the FEM path
    body = _poll(client, client.post("/study", json=_STUDY).json()["id"])
    assert body["status"] == "done"
    assert body["study"]["n_geometries"] == 1
    assert seen["diameters"] == _STUDY["diameters_um"]  # the real controls reached it


@pytest.mark.neuron
@pytest.mark.slow
def test_a_single_geometry_runs_real_neuron_on_the_analytical_tier(neuron_h):
    """The real threshold path, without FEM: a single diameter is not a geometry
    comparison, so the analytical tier is legitimate and the guard stays quiet."""
    from api.study_core import run_study
    from engine.field import AnalyticalBackend

    result = run_study(
        {**_STUDY, "diameters_um": [10.0], "pitches_um": [50.0]},
        backend=AnalyticalBackend(),  # real NEURON, analytical field, one geometry
    )
    assert result["n_geometries"] == 1
    assert all(p["cost_uA"] > 0 for p in result["points"])
