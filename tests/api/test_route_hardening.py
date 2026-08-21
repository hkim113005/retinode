"""Guards for the ways a route could answer *wrongly* rather than fail loudly.

Three of these four defects shared one shape: a request carrying a 3D electrode body
reached an analytical code path, which is blind to electrode geometry by construction,
and got the flat-disk answer back as though it were the body's. That is the same
silent-flat-frontier failure ``require_geometry_distinguishable`` exists to prevent in
the study path (docs/phase-8-findings.md) — these lock the API side of it. The fourth
is the input-validation floor: what a route must refuse before it ties up a worker.
"""

import pytest
from fastapi.testclient import TestClient

from api import create_app
from api.models import MAX_APERTURE_UM, MAX_GRID_POINTS, MIN_PITCH_UM, SweepControls
from api.routes.sweep import _cache_key

BODY = {"kind": "cylinder", "radius_um": 8.0, "height_um": 40.0}


def _fake_thresholds(*_a, **_k):
    from engine.cable.population import PopulationThresholds

    return PopulationThresholds("target", 10.0, {"off0": 20.0})


@pytest.fixture
def client():
    return TestClient(create_app(thresholds_provider=_fake_thresholds))


# --- a bodied scene must never be answered on the analytical tier -------------------


def test_compare_refuses_a_scorecard_for_a_bodied_scene(client):
    """It used to return the FLAT electrode's operating window for a 3D body."""
    r = client.post("/compare", json={"n": 9, "include_scorecard": True, "body": BODY})
    assert r.status_code == 422
    assert "FEM" in r.json()["detail"]


def test_compare_honours_the_callers_overlap_policy(client):
    """``overlap_policy`` was built into the scene but never passed to ``evaluate``,
    so a caller asking for 'displace' still got the reject path's OverlapConflict --
    as an uncaught 500, advising the very policy it had already set."""
    r = client.post(
        "/compare",
        json={"n": 9, "include_scorecard": True, "overlap_policy": "displace"},
    )
    assert r.status_code == 200  # no body => no conflict, and the kwarg is accepted


def test_sweep_refuses_a_bodied_scene(client):
    r = client.post(
        "/sweep",
        json={
            "n_amplitudes": 2,
            "amp_min_uA": 1,
            "amp_max_uA": 200,
            "spacing": "linear",
            "body": BODY,
        },
    )
    assert r.status_code == 422
    assert "analytical tier" in r.json()["detail"]


def test_sweep_cache_key_separates_shapes_and_policies():
    """The key omitted body/overlap_policy, so a bodied sweep collided with the flat
    entry and was served the flat curves instantly, flagged ``cached: true``."""
    flat = _cache_key(SweepControls())
    assert _cache_key(SweepControls(body=BODY)) != flat
    assert _cache_key(SweepControls(overlap_policy="displace")) != flat


# --- the study grid must be bounded before it reaches a worker ----------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"pitches_um": [MIN_PITCH_UM / 10]},  # tiles the aperture ~unboundedly
        {"aperture_um": MAX_APERTURE_UM * 10},
        {"diameters_um": [1.0] * 16, "pitches_um": [float(i + 10) for i in range(16)]},
        {"diameters_um": []},
        {"diameters_um": [-5.0]},
    ],
)
def test_study_refuses_an_unbounded_or_invalid_grid(client, payload):
    """Each of these used to be accepted. The sub-micron pitch is the sharp one: the
    lattice loops ``(2*ceil(aperture/pitch)+1)**2`` times, so an ~80-byte request
    occupied one of two worker slots forever, with no cancel endpoint."""
    assert client.post("/study", json=payload).status_code == 422


def test_study_accepts_the_default_grid(client):
    assert client.post("/study", json={}).status_code == 200
    assert len(SweepControls().model_dump()) > 0  # sanity: models still construct


def test_grid_cap_is_the_documented_product(client):
    """The cap is on the Cartesian product, not either axis alone."""
    n = int(MAX_GRID_POINTS**0.5)
    ok = {
        "diameters_um": [float(i + 5) for i in range(n)],
        "pitches_um": [float(i + 30) for i in range(n)],
    }
    assert client.post("/study", json=ok).status_code == 200


# --- non-finite floats: gt=0 does not exclude inf ----------------------------------


@pytest.mark.parametrize("raw", ['{"extent_um": 1e400, "n": 9}', '{"extent_um": NaN, "n": 21}'])
def test_compare_refuses_non_finite_floats(client, raw):
    """``float('inf') > 0`` is True, so ``Field(gt=0)`` let inf through and the grid
    came back all-``null`` in fields the schema declares non-nullable ``float``."""
    r = client.request(
        "POST", "/compare", content=raw, headers={"content-type": "application/json"}
    )
    assert r.status_code == 422


def test_a_non_finite_input_can_still_be_rendered_as_422(client):
    """Starlette renders JSON with ``allow_nan=False``, so echoing the bad input back
    made the 422 *itself* raise — a 500 for the input that most needed a clear error."""
    r = client.request(
        "POST",
        "/study",
        content='{"pitches_um": [NaN]}',
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]  # renders, rather than blowing up the encoder
