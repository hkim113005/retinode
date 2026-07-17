"""P7 S1: the /compare endpoint returns the same numbers the Dash view does, typed."""

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import create_app
from app.scene import build_scene
from app.views import field_grid, scorecard_data
from engine.cable.population import PopulationThresholds
from engine.eval import evaluate

_CONTROLS = {
    "layout": "single",
    "electrode_um": 10.0,
    "pitch_um": 60.0,
    "phase_width_us": 200.0,
    "neighbor_um": 40.0,
    "sigma_S_per_m": 1.0,
    "extent_um": 130.0,
    "n": 41,
}


def _fake_provider(target_uA, off):
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        return PopulationThresholds(patch.target_id, target_uA, dict(off))

    return provider


def _scene():
    return build_scene(
        layout="single", electrode_um=10.0, pitch_um=60.0,
        phase_width_us=200.0, neighbor_um=40.0, sigma_S_per_m=1.0,
    )


def test_health():
    assert TestClient(create_app()).get("/health").json() == {"status": "ok"}


def test_compare_field_matches_the_dash_view_exactly():
    client = TestClient(create_app())
    r = client.post("/compare", json=_CONTROLS)
    assert r.status_code == 200
    body = r.json()
    assert body["scorecard"] is None  # not requested -> no NEURON

    s = _scene()
    g = field_grid(s.array, s.config, s.conductivity, extent_um=130.0, n=41)
    assert np.allclose(np.array(body["field"]["ve_mV"]), g.ve_mV)
    assert np.allclose(np.array(body["field"]["xs_um"]), g.xs)
    assert np.allclose(np.array(body["field"]["ys_um"]), g.ys)
    assert body["field"]["vmax_mV"] == pytest.approx(float(np.abs(g.ve_mV).max()))
    # a single cathode makes Ve negative everywhere
    assert np.max(np.array(body["field"]["ve_mV"])) <= 0.0


def test_compare_scorecard_matches_the_dash_view_with_the_same_provider():
    provider = _fake_provider(8.0, {"neighbor": 12.0})
    client = TestClient(create_app(thresholds_provider=provider))
    r = client.post("/compare", json={**_CONTROLS, "n": 21, "include_scorecard": True})
    sc = r.json()["scorecard"]

    s = _scene()
    expected = scorecard_data(
        evaluate(s.patch, s.array, s.config, s.conductivity, thresholds_provider=provider)
    )
    assert sc["activated"] is True and expected["activated"] is True
    assert sc["target_uA"] == expected["target_uA"] == 8.0
    assert sc["off_min_uA"] == expected["off_min_uA"] == 12.0
    assert sc["ratio"] == expected["ratio"] == 1.5
    assert sc["limiting"] == expected["limiting"]


def test_compare_reports_no_activation_cleanly():
    provider = _fake_provider(None, {"neighbor": 12.0})
    client = TestClient(create_app(thresholds_provider=provider))
    r = client.post("/compare", json={**_CONTROLS, "n": 21, "include_scorecard": True})
    assert r.json()["scorecard"] == {
        "activated": False, "target_uA": None, "off_min_uA": None, "ratio": None,
        "window_lo_uA": None, "window_hi_uA": None, "usable_margin_uA": None,
        "usable": None, "limiting": None, "safety_ceiling_uA": None, "safe_at_target": None,
    }


def test_compare_rejects_invalid_controls():
    r = TestClient(create_app()).post("/compare", json={**_CONTROLS, "electrode_um": -1.0})
    assert r.status_code == 422  # pydantic validation, not a 500
