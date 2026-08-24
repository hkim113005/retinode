"""P2b: UI state → spec objects."""

from app.scene import build_array, build_config, build_patch, build_scene, cell_depth_um
from engine import spec


def test_single_array_is_one_disk_on_axis():
    a = build_array("single", 10.0, 60.0)
    assert len(a.electrodes) == 1
    assert a.electrodes[0].pos_um == (0.0, 0.0, 0.0)
    assert a.electrodes[0].size_um == 10.0


def test_bipolar_array_splits_by_pitch():
    a = build_array("bipolar", 12.0, 80.0)
    assert [e.pos_um[0] for e in a.electrodes] == [-40.0, 40.0]
    assert all(e.size_um == 12.0 for e in a.electrodes)


def test_single_config_is_monopolar_cathodic():
    c = build_config("single", 200.0)
    assert c.weight_map() == {"e0": -1.0}
    assert c.distant_return is True
    assert c.waveform.phase_width_us == 200.0


def test_bipolar_config_is_local_and_charge_balanced():
    c = build_config("bipolar", 150.0)
    assert c.weight_map() == {"e0": -1.0, "e1": 1.0}
    assert c.distant_return is False
    assert sum(c.weight_map().values()) == 0.0


def test_patch_is_target_plus_neighbour():
    p = build_patch(50.0)
    assert p.target_id == "target"
    assert {c.id for c in p.cells} == {"target", "neighbor"}
    neighbor = next(c for c in p.cells if c.id == "neighbor")
    assert neighbor.soma_um == (50.0, 0.0, 20.0)  # +z into tissue (D8)


def test_build_scene_assembles_all_four_specs():
    s = build_scene(
        layout="bipolar",
        electrode_um=10.0,
        pitch_um=60.0,
        phase_width_us=200.0,
        neighbor_um=40.0,
        sigma_S_per_m=1.5,
    )
    assert len(s.array.electrodes) == 2
    assert isinstance(s.config, spec.StimConfig)
    assert isinstance(s.patch, spec.RetinalPatch)
    assert s.conductivity.sigma_S_per_m == 1.5


def test_cells_sit_in_the_positive_z_tissue():
    """The array plane is z=0 and +z runs into the tissue (D8, docs/phase-6-plan.md).

    This is not cosmetic. Every Phase-6 3D predicate assumes it. `point_in_body`
    tests ``0 <= dz <= height_um``, so a cell at negative z can never be inside any
    electrode body. If this flips back, the overlap check silently matches nothing
    instead of failing, which is the worst way for it to break.
    """
    from engine.spec.body import Cylinder, point_in_body

    assert cell_depth_um() > 0
    scene = build_scene(
        layout="single", electrode_um=10.0, pitch_um=60.0,
        phase_width_us=200.0, neighbor_um=40.0, sigma_S_per_m=1.0,
    )
    assert all(c.soma_um[2] > 0 for c in scene.patch.cells)
    assert scene.patch.optic_disc_um[2] > 0  # the axon runs through tissue, not air

    # a pillar tall enough to swallow the target's soma must actually register
    target = scene.patch.target()
    pillar = Cylinder(radius_um=5.0, height_um=cell_depth_um() + 5.0)
    assert point_in_body(pillar, 0.0, 0.0, target.soma_um[2])
