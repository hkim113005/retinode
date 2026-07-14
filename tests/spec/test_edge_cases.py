"""Adversarial edge cases: non-finite values, unicode, empty collections, extremes."""

import math

import pytest

from engine import spec


def codes(problems) -> set[str]:
    return {p.code for p in problems}


# --- validation: non-finite values are caught -----------------------------


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_weight_is_rejected(bad):
    cfg = spec.StimConfig(
        weights=(("a", bad), ("b", 1.0)), waveform=spec.Waveform(phase_width_us=100.0)
    )
    assert "non-finite-value" in codes(spec.validate(cfg))


def test_nan_weight_does_not_masquerade_as_balanced():
    # Regression: math.fsum([nan]) is nan and abs(nan) > atol is False, so
    # without the finite check a NaN weight would validate clean and then blow
    # up at serialization.
    cfg = spec.StimConfig(weights=(("a", math.nan),), waveform=spec.Waveform(phase_width_us=100.0))
    assert spec.has_errors(spec.validate(cfg))


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_non_finite_waveform_is_rejected(bad):
    assert "non-finite-value" in codes(spec.validate(spec.Waveform(phase_width_us=bad)))


def test_non_finite_conductivity_is_rejected():
    assert "non-finite-value" in codes(
        spec.validate(spec.HomogeneousConductivity(sigma_S_per_m=math.nan))
    )
    layered = spec.LayeredConductivity(
        layers=(spec.Layer(sigma_S_per_m=math.inf, thickness_um=10.0),)
    )
    assert "non-finite-value" in codes(spec.validate(layered))


def test_non_finite_electrode_is_rejected():
    e = spec.Electrode(id="e", pos_um=(math.nan, 0.0, 0.0), shape="disk", size_um=10.0)
    assert "non-finite-value" in codes(spec.validate(e))


def test_coincident_electrodes_overlap():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="a", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="b", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    assert "electrode-overlap" in codes(spec.validate(array))


# --- serialization / hashing edges -----------------------------------------


def test_type_tag_value_collision_round_trips():
    # An id whose *value* is "__type__" must not confuse the decoder.
    e = spec.Electrode(id="__type__", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=1.0)
    assert spec.from_json(spec.to_json(e)) == e


def test_unicode_ids_round_trip_and_hash_stably():
    e = spec.Electrode(id="cé中\U0001f9e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=1.0)
    restored = spec.from_json(spec.to_json(e))
    assert restored == e
    assert spec.spec_hash(restored) == spec.spec_hash(e)


@pytest.mark.parametrize(
    "obj",
    [
        spec.ElectrodeArray(electrodes=()),
        spec.LayeredConductivity(layers=()),
        spec.StimConfig(weights=(), waveform=spec.Waveform(phase_width_us=100.0)),
        spec.RetinalPatch(cells=(), target_id="t"),
        spec.StudyDefinition(sweeps=()),
        spec.RGC(id="a", cell_type="x", soma_um=(0.0, 0.0, 0.0), axon_um=()),
    ],
)
def test_empty_collections_round_trip(obj):
    assert spec.from_json(spec.to_json(obj)) == obj


@pytest.mark.parametrize("value", [1e300, 1e-300, -1e300, 5e-324, 2.2250738585072014e-308])
def test_extreme_finite_floats_round_trip(value):
    wf = spec.Waveform(phase_width_us=value)
    assert spec.from_json(spec.to_json(wf)).phase_width_us == value


def test_empty_array_and_empty_config_hash_differently():
    empty_array = spec.ElectrodeArray(electrodes=())
    empty_config = spec.StimConfig(weights=(), waveform=spec.Waveform(phase_width_us=100.0))
    assert spec.spec_hash(empty_array) != spec.spec_hash(empty_config)
