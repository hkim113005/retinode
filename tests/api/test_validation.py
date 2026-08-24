"""P7 S6: the Validation trust panel serves the committed reproductions report."""

from fastapi.testclient import TestClient

from api import create_app
from app.views import load_validation_report


def test_validation_serves_the_committed_report():
    body = TestClient(create_app()).get("/validation").json()
    # the API must serve exactly what the Dash view reads: one report, one truth
    assert body == load_validation_report()
    assert body["n_total"] >= 1
    assert body["n_pass"] == sum(1 for r in body["reproductions"] if r["passed"])
    assert len(body["reproductions"]) == body["n_total"]


def test_every_reproduction_carries_its_evidence():
    reps = TestClient(create_app()).get("/validation").json()["reproductions"]
    for r in reps:
        # a skeptic needs the claim, where it came from, and what was measured
        assert r["name"] and r["source"] and r["criterion"]
        assert isinstance(r["passed"], bool)
        assert "measured" in r
