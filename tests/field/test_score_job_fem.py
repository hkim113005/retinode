"""(fem) The conda-side FEM scorecard the /score route dispatches for a 3D electrode.

Runs in the ``retinode-fem`` env (DOLFINx + NEURON). This is the end-to-end proof of
the custom-shape UI path's backend: a bodied scene scores on the FEM tier, its window
differs from a flat disk (the geometry effect the analytical point source can't see),
and the overlap policy governs a penetrating body. Small/quick where possible, but a
real FEM solve + NEURON threshold search — so it is fem+slow."""

from __future__ import annotations

import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

from api.score_job import solve_scorecard  # noqa: E402
from engine.eval.overlap import OverlapConflict  # noqa: E402

pytestmark = [pytest.mark.fem, pytest.mark.slow]

_BASE = {
    "layout": "single",
    "electrode_um": 10.0,
    "pitch_um": 60.0,
    "phase_width_us": 200.0,
    "neighbor_um": 40.0,
    "sigma_S_per_m": 1.0,
}


def test_flat_disk_scores_a_sane_window():
    sc = solve_scorecard({**_BASE, "body": {"kind": "none"}})
    assert sc["activated"]
    assert sc["target_uA"] > 0.0
    assert sc["off_target_thresholds_uA"]["neighbor"] > sc["target_uA"]  # selective


def test_a_tip_pillar_scores_and_differs_from_the_flat_disk():
    """The pillar concentrates injection at its deep tip, so its operating window is
    measurably different from a flat disk of the same footprint — the whole reason
    shaped electrodes are worth authoring. It penetrates the ~20 µm cell plane, so it
    needs the displace policy to sever the in-metal compartments."""
    tip_pillar = {"kind": "cylinder", "radius_um": 5.0, "height_um": 30.0, "conductive_faces": "tip"}  # noqa: E501
    flat = solve_scorecard({**_BASE, "body": {"kind": "none"}})
    pillar = solve_scorecard({**_BASE, "body": tip_pillar, "overlap_policy": "displace"})
    assert pillar["activated"]
    assert pillar["target_uA"] != pytest.approx(flat["target_uA"], rel=1e-3)


def test_a_penetrating_pillar_is_rejected_by_default():
    """The default reject policy refuses a cell embedded in the metal — the safe
    default the UI surfaces as an error rather than a silently wrong score."""
    with pytest.raises(OverlapConflict):
        solve_scorecard(
            {
                **_BASE,
                "body": {"kind": "cylinder", "radius_um": 5.0, "height_um": 30.0},
                "overlap_policy": "reject",
            }
        )
