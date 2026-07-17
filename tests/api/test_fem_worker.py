"""P7 S3b: the FEM dispatch — subprocess protocol, divergence, and error handling.

These mock the subprocess (no conda/DOLFINx needed), so they run in the fast job.
The real conda-side solve is exercised by tests/field/test_fem_dispatch.py (fem).
"""

import json
import types

import numpy as np
import pytest
from fastapi.testclient import TestClient

from api import create_app
from api.fem_worker import solve_accurate_field
from api.models import FieldGridResponse, SceneControls
from api.service import field_grid_payload
from app.scene import build_scene

_CONTROLS = SceneControls(layout="single", electrode_um=10.0, n=21, extent_um=130.0)


def _analytical_grid(controls: SceneControls) -> dict:
    s = build_scene(
        layout=controls.layout, electrode_um=controls.electrode_um, pitch_um=controls.pitch_um,
        phase_width_us=controls.phase_width_us, neighbor_um=controls.neighbor_um,
        sigma_S_per_m=controls.sigma_S_per_m,
    )
    g = field_grid_payload(
        s.array, s.config, s.conductivity, extent_um=controls.extent_um, n=controls.n
    )
    return {"xs_um": g.xs_um, "ys_um": g.ys_um, "ve_mV": g.ve_mV, "vmax_mV": g.vmax_mV}


def _runner_writing(grid: dict, returncode: int = 0, stderr: str = ""):
    """A fake subprocess.run that writes ``grid`` to the output file in argv."""

    def runner(cmd, input=None, capture_output=None, text=None, timeout=None, cwd=None):
        if returncode == 0:
            with open(cmd[-1], "w") as f:
                json.dump(grid, f)
        return types.SimpleNamespace(returncode=returncode, stderr=stderr, stdout="")

    return runner


def test_dispatch_parses_the_subprocess_result():
    grid = _analytical_grid(_CONTROLS)  # pretend the FEM returned the analytical field
    field, divergence = solve_accurate_field(_CONTROLS, runner=_runner_writing(grid))
    assert isinstance(field, FieldGridResponse)
    assert len(field.ve_mV) == 21
    assert divergence == pytest.approx(0.0, abs=1e-6)  # identical -> zero divergence


def test_divergence_is_measured_against_analytical():
    grid = _analytical_grid(_CONTROLS)
    scaled = {**grid, "ve_mV": (np.array(grid["ve_mV"]) * 0.8).tolist()}  # FEM 20% weaker
    field, divergence = solve_accurate_field(_CONTROLS, runner=_runner_writing(scaled))
    assert divergence == pytest.approx(20.0, abs=0.5)


def test_a_failed_subprocess_raises_a_clear_error():
    runner = _runner_writing({}, returncode=1, stderr="boom\nRuntimeError: no mesh")
    with pytest.raises(RuntimeError, match="FEM solve failed"):
        solve_accurate_field(_CONTROLS, runner=runner)


def test_accurate_field_endpoint_flows_through_the_job(monkeypatch):
    # monkeypatch the solver so the endpoint's job doesn't shell out to conda
    grid = _analytical_grid(_CONTROLS)

    def fake_solve(controls, **_):
        return FieldGridResponse(**grid), 3.5

    monkeypatch.setattr("api.routes.field.solve_accurate_field", fake_solve)
    client = TestClient(create_app())
    submitted = client.post("/field/accurate", json=_CONTROLS.model_dump()).json()

    import time

    deadline = time.time() + 5
    body = submitted
    while body["status"] == "running" and time.time() < deadline:
        time.sleep(0.02)
        body = client.get(f"/jobs/{submitted['id']}").json()
    assert body["status"] == "done"
    assert body["field"] is not None and len(body["field"]["ve_mV"]) == 21
    assert body["max_divergence_pct"] == pytest.approx(3.5)
    assert body["scorecard"] is None  # an accurate-field job carries no scorecard
