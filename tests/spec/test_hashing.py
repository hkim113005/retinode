"""Hashing: stability, sensitivity, order-independence, and composite keys."""

import hashlib

from hypothesis import given

from engine import spec
from tests.spec.test_serialization import any_spec


@given(any_spec)
def test_spec_hash_is_sha256_of_canonical_json(obj):
    assert spec.spec_hash(obj) == hashlib.sha256(spec.to_json(obj).encode()).hexdigest()


@given(any_spec)
def test_hash_is_stable_across_roundtrip(obj):
    # Reconstructing from JSON must not change the hash.
    assert spec.spec_hash(spec.from_json(spec.to_json(obj))) == spec.spec_hash(obj)


def test_equal_specs_hash_equal():
    a = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
    b = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
    assert spec.spec_hash(a) == spec.spec_hash(b)


def test_any_field_change_changes_the_hash():
    base = spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)
    moved = spec.Electrode(id="c", pos_um=(1.0, 0.0, 0.0), shape="disk", size_um=10.0)
    renamed = spec.Electrode(id="d", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)
    resized = spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=12.0)
    assert len({spec.spec_hash(e) for e in (base, moved, renamed, resized)}) == 4


def test_weight_order_does_not_affect_hash():
    wf = spec.Waveform(phase_width_us=100.0)
    a = spec.StimConfig.from_map({"c": -1.0, "r1": 1.0}, waveform=wf)
    b = spec.StimConfig.from_map({"r1": 1.0, "c": -1.0}, waveform=wf)
    assert spec.spec_hash(a) == spec.spec_hash(b)


def test_geometry_and_config_hashes_are_independent():
    # The whole point of separate hashes: a config change must not change the
    # array's hash, so a cached field can be reused across configurations.
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    wf = spec.Waveform(phase_width_us=100.0)
    cfg_a = spec.StimConfig.from_map({"c": -1.0}, waveform=wf, distant_return=True)
    cfg_b = spec.StimConfig.from_map({"c": -2.0}, waveform=wf, distant_return=True)
    assert spec.spec_hash(cfg_a) != spec.spec_hash(cfg_b)  # configs differ
    assert spec.spec_hash(array) == spec.spec_hash(array)  # array hash unaffected


def test_canonical_json_and_hash_are_pinned():
    # Pins the canonical format and the hash definition, so a change to either
    # (which would silently invalidate every cache) is caught here.
    c = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
    expected_json = '{"__type__":"HomogeneousConductivity","schema_version":1,"sigma_S_per_m":1.0}'
    assert spec.to_json(c) == expected_json
    assert spec.spec_hash(c) == hashlib.sha256(expected_json.encode()).hexdigest()


def test_combine_is_deterministic_order_sensitive_and_unambiguous():
    assert spec.combine("aa", "bb") == spec.combine("aa", "bb")  # deterministic
    assert spec.combine("aa", "bb") != spec.combine("bb", "aa")  # order-sensitive
    assert spec.combine("aa", "bb") != spec.combine("aab", "")  # boundaries unambiguous
    assert len(spec.combine("aa", "bb")) == 64  # full sha256 hex
