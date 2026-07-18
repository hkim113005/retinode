"""The /score route's tier decision: a bodied scene goes to the FEM env, a flat one
stays on the fast in-process analytical path.

The FEM dispatch itself (api.score_worker) is unit-tested with a fake subprocess in
test_score_worker.py; here we only assert the route picks the right path — mocking
run_score_job so no conda interpreter is needed."""

import time

import pytest
from fastapi.testclient import TestClient

from api import create_app
from api.models import ScorecardResponse


def _fake_provider(target_uA, off):
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        from engine.cable.population import PopulationThresholds

        return PopulationThresholds(patch.target_id, target_uA, off)

    return provider


def _poll(client, job_id, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.02)
    raise AssertionError("job did not finish")


_PILLAR = {"kind": "cylinder", "radius_um": 5.0, "height_um": 30.0, "conductive_faces": "tip"}


def test_a_bodied_scene_dispatches_to_the_fem_worker(monkeypatch):
    calls = {}

    def fake_run_score_job(controls, report, **_):
        calls["body_kind"] = controls.body.kind
        report(0.5, "fem")
        return ScorecardResponse(activated=True, target_uA=7.83, usable_margin_uA=6.05)

    # patch where the route looked it up
    monkeypatch.setattr("api.routes.score.run_score_job", fake_run_score_job)
    # a fake provider is injected, but the bodied path must ignore it and go to FEM
    client = TestClient(create_app(thresholds_provider=_fake_provider(999.0, {"neighbor": 999.0})))
    submitted = client.post("/score", json={"body": _PILLAR}).json()
    body = _poll(client, submitted["id"])

    assert body["status"] == "done"
    assert calls["body_kind"] == "cylinder"  # the FEM worker was called with the body
    assert body["scorecard"]["target_uA"] == 7.83  # its result, not the analytical provider's


def test_a_flat_scene_never_touches_the_fem_worker(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("a flat disk must not dispatch to FEM")

    monkeypatch.setattr("api.routes.score.run_score_job", boom)
    client = TestClient(create_app(thresholds_provider=_fake_provider(8.0, {"neighbor": 12.0})))
    body = _poll(client, client.post("/score", json={}).json()["id"])  # no body

    assert body["status"] == "done"
    assert body["scorecard"]["target_uA"] == 8.0  # the analytical provider's number


def test_body_and_flat_do_not_share_a_cache_key(monkeypatch):
    monkeypatch.setattr(
        "api.routes.score.run_score_job",
        lambda c, r, **_: ScorecardResponse(activated=True, target_uA=1.0),
    )
    client = TestClient(create_app(thresholds_provider=_fake_provider(8.0, {"neighbor": 12.0})))
    flat = _poll(client, client.post("/score", json={}).json()["id"])
    pillar = _poll(client, client.post("/score", json={"body": _PILLAR}).json()["id"])
    # different scores prove they did not collide on one cache entry
    assert flat["scorecard"]["target_uA"] == 8.0
    assert pillar["scorecard"]["target_uA"] == 1.0


@pytest.mark.parametrize("policy", ["reject", "displace"])
def test_overlap_policy_threads_through_to_the_worker(monkeypatch, policy):
    seen = {}

    def fake(controls, report, **_):
        seen["policy"] = controls.overlap_policy
        return ScorecardResponse(activated=False)

    monkeypatch.setattr("api.routes.score.run_score_job", fake)
    client = TestClient(create_app())
    submitted = client.post("/score", json={"body": _PILLAR, "overlap_policy": policy}).json()
    _poll(client, submitted["id"])
    assert seen["policy"] == policy
