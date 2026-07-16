"""P6 S4: cell <-> electrode-body overlap detection and policy (pure geometry)."""

import pytest

from engine.eval import (
    OverlapConflict,
    check_overlap,
    resolve_overlap,
)
from engine.spec import ArrayPlacement, Cylinder, Electrode, ElectrodeArray


def _pillar_array(pos=(40.0, 0.0, 0.0), r=5.0, h=30.0, placement=None):
    return ElectrodeArray(
        electrodes=(
            Electrode(id="P", pos_um=pos, shape="disk", size_um=0.0, body=Cylinder(r, h)),
            Electrode(id="F", pos_um=(-40.0, 0.0, 0.0), shape="disk", size_um=12.0),  # flat
        ),
        placement=placement,
    )


def test_detects_compartments_inside_a_penetrating_electrode():
    cells = {
        "target": [(40.0, 0.0, 10.0), (40.0, 0.0, 20.0), (43.0, 0.0, 15.0)],  # all inside
        "safe": [(40.0, 0.0, 45.0), (0.0, 0.0, 20.0)],  # outside
    }
    rep = check_overlap(_pillar_array(), cells)
    assert rep.has_conflict
    assert rep.inside_compartments("target") == {0, 1, 2}
    assert rep.inside_compartments("safe") == set()
    assert all(f.electrode_id == "P" for f in rep.conflicts)  # flat electrode never conflicts


def test_flags_near_contact_just_outside_the_surface():
    # a compartment 1 um outside the r=5 wall (at x = 40 + 6) is near-contact, not inside
    rep = check_overlap(_pillar_array(), {"c": [(46.0, 0.0, 15.0)]}, near_contact_eps_um=1.5)
    assert not rep.has_conflict
    assert len(rep.near_contacts) == 1
    assert rep.near_contacts[0].near_contact and not rep.near_contacts[0].inside


def test_a_comfortable_gap_is_not_flagged():
    rep = check_overlap(_pillar_array(), {"c": [(60.0, 0.0, 15.0)]}, near_contact_eps_um=1.0)
    assert rep.flags == ()


def test_placement_moves_the_body_before_the_check():
    # the array is planted +100 in x, so the pillar is now at x=140; a compartment
    # at x=140 is inside it, but the same compartment was clear before the offset.
    placed = _pillar_array(placement=ArrayPlacement(offset_um=(100.0, 0.0, 0.0)))
    rep = check_overlap(placed, {"c": [(140.0, 0.0, 15.0)]})
    assert rep.has_conflict
    assert check_overlap(_pillar_array(), {"c": [(140.0, 0.0, 15.0)]}).flags == ()


def test_reject_policy_raises_on_a_conflict():
    rep = check_overlap(_pillar_array(), {"t": [(40.0, 0.0, 15.0)]})
    with pytest.raises(OverlapConflict, match="inside electrode 'P'"):
        resolve_overlap(rep, "reject")


def test_displace_policy_reports_the_compartments_to_drop():
    cells = {"t": [(40.0, 0.0, 10.0), (40.0, 0.0, 20.0), (0.0, 0.0, 20.0)]}  # 0,1 in; 2 out
    rep = check_overlap(_pillar_array(), cells)
    assert resolve_overlap(rep, "displace") == {"t": {0, 1}}


def test_no_conflict_resolves_to_nothing_for_either_policy():
    rep = check_overlap(_pillar_array(), {"c": [(0.0, 0.0, 20.0)]})  # nowhere near the pillar
    assert resolve_overlap(rep, "reject") == {}
    assert resolve_overlap(rep, "displace") == {}


def test_a_flat_only_array_never_conflicts():
    flat = ElectrodeArray(
        electrodes=(Electrode(id="F", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    rep = check_overlap(flat, {"c": [(0.0, 0.0, 0.0), (0.0, 0.0, 5.0)]})
    assert rep.flags == () and not rep.has_conflict
