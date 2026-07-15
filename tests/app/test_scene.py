"""P2b: UI state → spec objects."""

from app.scene import build_array, build_config, build_patch, build_scene
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
    assert neighbor.soma_um == (50.0, 0.0, -20.0)


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
