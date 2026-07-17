"""P8 S1: the amplitude sweep job — submit, poll, cache."""

import time

from fastapi.testclient import TestClient

from api import create_app
from api.service import sweep_payload
from engine.study.activation import AmplitudeSweep, CellActivation

_CONTROLS = {
    "layout": "single",
    "electrode_um": 10.0,
    "pitch_um": 60.0,
    "phase_width_us": 200.0,
    "neighbor_um": 40.0,
    "sigma_S_per_m": 1.0,
    "amp_min_uA": 1.0,
    "amp_max_uA": 100.0,
    "n_amplitudes": 4,
    "spacing": "linear",
}


def _poll(client, job, tries=80):
    for _ in range(tries):
        if job["status"] != "running":
            return job
        time.sleep(0.05)
        job = client.get(f"/jobs/{job['id']}").json()
    raise AssertionError("job never finished")


def test_sweep_payload_keeps_the_grid_crossing_apart_from_a_threshold():
    """The crossing is grid resolution; the scorecard's bisection is the accurate
    number. They must stay distinct fields with distinct names."""
    sweep = AmplitudeSweep(
        amplitudes_uA=(1.0, 2.0, 3.0, 4.0),
        cells=(
            CellActivation("target", True, (False, True, True, True), (None, "ais", "ais", "ais")),
            CellActivation(
                "neighbor", False, (False, False, False, True), (None, None, None, "soma")
            ),
            CellActivation(
                "blocker", False, (False, True, True, False), (None, "ais", "ais", None)
            ),
        ),
    )
    body = sweep_payload(sweep)
    assert body.amplitudes_uA == [1.0, 2.0, 3.0, 4.0]
    by_id = {c.cell_id: c for c in body.curves}
    assert by_id["target"].crossing_uA == 2.0
    assert by_id["target"].is_target is True
    assert by_id["neighbor"].crossing_uA == 4.0  # the bystander joins last
    assert by_id["target"].initiation_region == [None, "ais", "ais", "ais"]
    # depolarization block is carried, not smoothed away
    assert by_id["blocker"].blocks is True
    assert by_id["target"].blocks is False
    # and no "fraction" field exists to be dishonest with
    assert not hasattr(body, "target_fraction")


def test_sweep_rejects_a_grid_that_is_not_a_curve():
    client = TestClient(create_app())
    assert client.post("/sweep", json={**_CONTROLS, "n_amplitudes": 1}).status_code == 422
    assert client.post("/sweep", json={**_CONTROLS, "amp_min_uA": 0.0}).status_code == 422
    # the cap is real: an unbounded grid would stop this being a "seconds" job
    assert client.post("/sweep", json={**_CONTROLS, "n_amplitudes": 5000}).status_code == 422


def test_sweep_runs_as_a_job_and_caches_an_identical_request(monkeypatch):
    calls = {"n": 0}

    def fake_sweep(patch, array, config, conductivity, *, amplitudes_uA, on_amplitude=None, **_):
        calls["n"] += 1
        for i, a in enumerate(amplitudes_uA):
            if on_amplitude:
                on_amplitude(i, a)
        return AmplitudeSweep(
            amplitudes_uA=tuple(amplitudes_uA),
            cells=(
                CellActivation("target", True, tuple(a > 30 for a in amplitudes_uA),
                               tuple("ais" if a > 30 else None for a in amplitudes_uA)),
            ),
        )

    monkeypatch.setattr("api.routes.sweep.amplitude_sweep", fake_sweep)
    client = TestClient(create_app())

    job = _poll(client, client.post("/sweep", json=_CONTROLS).json())
    assert job["status"] == "done", job.get("error")
    assert job["cached"] is False
    assert job["sweep"]["amplitudes_uA"] == [1.0, 34.0, 67.0, 100.0]
    assert job["sweep"]["curves"][0]["activated"] == [False, True, True, True]
    assert calls["n"] == 1

    # an identical scene + grid is served from the cache, not re-run
    again = _poll(client, client.post("/sweep", json=_CONTROLS).json())
    assert again["status"] == "done"
    assert again["cached"] is True
    assert calls["n"] == 1

    # a different grid is a different answer, so it must re-run
    _poll(client, client.post("/sweep", json={**_CONTROLS, "n_amplitudes": 5}).json())
    assert calls["n"] == 2
