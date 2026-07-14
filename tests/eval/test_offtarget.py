"""Off-target selection: soma radius, axon proximity, nearest-N cap."""

from engine import spec
from engine.eval import OffTargetSet, select_off_targets

ARRAY = spec.ElectrodeArray(
    electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)


def patch_with(*cells, target_id="t"):
    return spec.RetinalPatch(cells=cells, target_id=target_id)


def rgc(cid, xyz, axon=()):
    return spec.RGC(id=cid, cell_type="parasol_on", soma_um=xyz, axon_um=axon)


def ids(cells):
    return {c.id for c in cells}


def test_selection_by_soma_radius_excludes_target_and_far_cells():
    patch = patch_with(
        rgc("t", (0.0, 0.0, -20.0)),
        rgc("near", (30.0, 0.0, -20.0)),
        rgc("far", (500.0, 0.0, -20.0)),
    )
    selected = select_off_targets(
        patch, ARRAY, OffTargetSet(soma_radius_um=120.0, axon_proximity_um=None)
    )
    assert ids(selected) == {"near"}


def test_axon_proximity_includes_a_far_soma_with_a_nearby_axon():
    # Soma is far, but its axon passes right over the electrode at the origin.
    patch = patch_with(
        rgc("t", (0.0, 0.0, -20.0)),
        rgc("bundle", (500.0, 0.0, -20.0), axon=((500.0, 0.0, -20.0), (0.0, 0.0, 0.0))),
        rgc("noaxon", (600.0, 0.0, -20.0)),  # far soma, no axon -> never off-target
    )
    with_axon = select_off_targets(
        patch, ARRAY, OffTargetSet(soma_radius_um=120.0, axon_proximity_um=30.0)
    )
    assert ids(with_axon) == {"bundle"}
    # Ignoring axons, the far soma is not off-target.
    without_axon = select_off_targets(
        patch, ARRAY, OffTargetSet(soma_radius_um=120.0, axon_proximity_um=None)
    )
    assert ids(without_axon) == set()


def test_max_soma_count_keeps_the_nearest():
    patch = patch_with(
        rgc("t", (0.0, 0.0, -20.0)),
        rgc("a", (10.0, 0.0, -20.0)),
        rgc("b", (20.0, 0.0, -20.0)),
        rgc("c", (30.0, 0.0, -20.0)),
    )
    selected = select_off_targets(
        patch, ARRAY, OffTargetSet(soma_radius_um=120.0, max_soma_count=2, axon_proximity_um=None)
    )
    assert ids(selected) == {"a", "b"}
