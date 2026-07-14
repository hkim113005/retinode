"""The spec objects construct, expose their helpers, and are immutable."""

from dataclasses import FrozenInstanceError

import pytest

from engine import spec


def make_array() -> spec.ElectrodeArray:
    return spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="r1", pos_um=(30.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )


def test_all_five_objects_construct():
    array = make_array()
    wf = spec.Waveform(phase_width_us=100.0)
    cfg = spec.StimConfig.from_map({"c": -1.0, "r1": 1.0}, waveform=wf)
    cond = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
    patch = spec.RetinalPatch(
        cells=(spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),),
        target_id="t",
    )
    study = spec.StudyDefinition(sweeps=(spec.Sweep(path="x", values=(1.0, 2.0)),))

    assert array.ids() == ("c", "r1")
    assert cfg.weight_map() == {"c": -1.0, "r1": 1.0}
    assert cond.sigma_S_per_m == 1.0
    assert patch.target().id == "t"
    assert study.tier == "analytical"


def test_electrode_array_lookup():
    array = make_array()
    assert array.by_id("r1").pos_um == (30.0, 0.0, 0.0)
    with pytest.raises(KeyError):
        array.by_id("missing")


def test_patch_target_missing_raises():
    patch = spec.RetinalPatch(
        cells=(spec.RGC(id="a", cell_type="x", soma_um=(0.0, 0.0, 0.0)),),
        target_id="nope",
    )
    with pytest.raises(KeyError):
        patch.target()


def test_from_map_is_canonical_and_reversible():
    wf = spec.Waveform(phase_width_us=100.0)
    cfg = spec.StimConfig.from_map({"r1": 1.0, "c": -1.0}, waveform=wf)
    # Stored sorted by id regardless of input order, so serialization is canonical.
    assert list(cfg.weights) == sorted(cfg.weights)
    assert cfg.weights[0][0] == "c"
    # And it round-trips back to the original mapping.
    assert cfg.weight_map() == {"c": -1.0, "r1": 1.0}


def test_sweep_linspace_endpoints_and_count():
    s = spec.Sweep.linspace("p", 50.0, 200.0, 4)
    assert s.values == (50.0, 100.0, 150.0, 200.0)
    # Degenerate single-point case.
    assert spec.Sweep.linspace("p", 5.0, 9.0, 1).values == (5.0,)


def test_frozen_objects_reject_mutation():
    electrode = make_array().electrodes[0]
    with pytest.raises(FrozenInstanceError):
        electrode.size_um = 99.0
