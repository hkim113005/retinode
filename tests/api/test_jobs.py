"""P7 S3: the async job model. The scorecard runs as a job, cached by scene."""

import time

import pytest
from fastapi.testclient import TestClient

from api import create_app
from api.jobs import JobRegistry
from engine.cable.population import PopulationThresholds

_CONTROLS = {
    "layout": "single",
    "electrode_um": 10.0,
    "pitch_um": 60.0,
    "phase_width_us": 200.0,
    "neighbor_um": 40.0,
    "sigma_S_per_m": 1.0,
}


def _fake_provider(target_uA, off):
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        return PopulationThresholds(patch.target_id, target_uA, dict(off))

    return provider


def _poll(client, job_id, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


# --- the registry in isolation ------------------------------------------------


def test_registry_runs_a_task_and_caches_by_key():
    reg = JobRegistry()
    calls = {"n": 0}

    def task(report):
        report(0.5, "half")
        calls["n"] += 1
        return {"value": 42}

    job = reg.submit("k", task)
    deadline = time.time() + 2
    while reg.get(job.id).status == "running" and time.time() < deadline:
        time.sleep(0.01)
    done = reg.get(job.id)
    assert done.status == "done" and done.result == {"value": 42}

    # a second submit with the same key is served from cache, so the task doesn't re-run
    again = reg.submit("k", task)
    assert again.status == "done" and again.cached and again.result == {"value": 42}
    assert calls["n"] == 1


def test_registry_records_task_failure():
    reg = JobRegistry()

    def boom(_report):
        raise ValueError("nope")

    job = reg.submit("bad", boom)
    deadline = time.time() + 2
    while reg.get(job.id).status == "running" and time.time() < deadline:
        time.sleep(0.01)
    failed = reg.get(job.id)
    assert failed.status == "error" and "nope" in failed.error


# --- the endpoints ------------------------------------------------------------


def test_score_runs_as_a_job_and_polls_to_a_result():
    client = TestClient(create_app(thresholds_provider=_fake_provider(8.0, {"neighbor": 12.0})))
    submitted = client.post("/score", json=_CONTROLS).json()
    assert submitted["status"] in ("running", "done")
    body = _poll(client, submitted["id"])
    assert body["status"] == "done"
    sc = body["scorecard"]
    assert sc["activated"] and sc["target_uA"] == 8.0 and sc["off_min_uA"] == 12.0


def test_score_resubmit_is_served_from_cache():
    client = TestClient(create_app(thresholds_provider=_fake_provider(8.0, {"neighbor": 12.0})))
    _poll(client, client.post("/score", json=_CONTROLS).json()["id"])  # warm the cache
    again = client.post("/score", json=_CONTROLS).json()
    assert again["status"] == "done" and again["cached"] is True
    assert again["scorecard"]["target_uA"] == 8.0


def test_unknown_job_is_404():
    assert TestClient(create_app()).get("/jobs/nope").status_code == 404


@pytest.mark.neuron
@pytest.mark.slow
def test_score_job_runs_a_real_threshold_search(neuron_h):
    # end-to-end: the default provider (real NEURON population solve) through the job.
    client = TestClient(create_app())
    body = _poll(client, client.post("/score", json=_CONTROLS).json()["id"], timeout=120.0)
    assert body["status"] == "done"
    assert body["scorecard"]["activated"] and body["scorecard"]["target_uA"] > 0.0
