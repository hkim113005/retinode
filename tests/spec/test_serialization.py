"""Serialization: round-trip for every object, canonical output, and edge cases."""

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine import spec

# --- strategies: one per object, then any_spec over all of them ------------

finite = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)
vec3 = st.tuples(finite, finite, finite)
ids = st.text(min_size=1, max_size=5)

_disk = st.builds(
    spec.Electrode,
    id=ids,
    pos_um=vec3,
    shape=st.sampled_from(["disk", "square", "hex"]),
    size_um=finite,
    normal=vec3,
)
_poly = st.builds(
    spec.Electrode,
    id=ids,
    pos_um=vec3,
    shape=st.just("poly"),
    size_um=finite,
    boundary_um=st.lists(vec3, min_size=3, max_size=5).map(tuple),
)
electrode = st.one_of(_disk, _poly)
array = st.builds(spec.ElectrodeArray, electrodes=st.lists(electrode, max_size=4).map(tuple))

waveform = st.builds(
    spec.Waveform,
    phase_width_us=finite,
    amplitude_scale_uA=finite,
    interphase_gap_us=finite,
    cathodic_first=st.booleans(),
)
stimconfig = st.builds(
    spec.StimConfig,
    weights=st.lists(st.tuples(ids, finite), max_size=4).map(tuple),
    waveform=waveform,
    distant_return=st.booleans(),
)

layer = st.builds(
    spec.Layer,
    sigma_S_per_m=finite,
    thickness_um=finite,
    anisotropy=st.one_of(st.none(), vec3),
)
homogeneous = st.builds(spec.HomogeneousConductivity, sigma_S_per_m=finite)
layered = st.builds(spec.LayeredConductivity, layers=st.lists(layer, max_size=3).map(tuple))

rgc = st.builds(
    spec.RGC,
    id=ids,
    cell_type=ids,
    soma_um=vec3,
    dendrite_diam_um=st.one_of(st.none(), finite),
    axon_um=st.lists(vec3, max_size=3).map(tuple),
)
patch = st.builds(
    spec.RetinalPatch,
    cells=st.lists(rgc, max_size=3).map(tuple),
    target_id=ids,
    optic_disc_um=st.one_of(st.none(), vec3),
)

sweep = st.builds(
    spec.Sweep, path=st.text(max_size=8), values=st.lists(finite, max_size=4).map(tuple)
)
study = st.builds(
    spec.StudyDefinition,
    sweeps=st.lists(sweep, max_size=3).map(tuple),
    tier=st.sampled_from(["analytical", "fem", "cross_checked"]),
    objectives=st.lists(ids, max_size=3).map(tuple),
)

any_spec = st.one_of(
    electrode, array, waveform, stimconfig, layer, homogeneous, layered, rgc, patch, sweep, study
)


@given(any_spec)
def test_roundtrip_equals_original(obj):
    assert spec.from_json(spec.to_json(obj)) == obj


@given(any_spec)
def test_roundtrip_preserves_tuple_types(obj):
    # Decoded collections must be tuples (frozen dataclass equality is by value,
    # but downstream code and hashing rely on the concrete tuple type).
    decoded = spec.from_json(spec.to_json(obj))
    assert type(decoded) is type(obj)


# --- canonical / determinism -----------------------------------------------


def test_output_is_deterministic_and_key_sorted():
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    s1 = spec.to_json(array)
    s2 = spec.to_json(array)
    assert s1 == s2
    # __type__ sorts before the fields; keys are sorted throughout.
    assert s1.startswith('{"__type__":"ElectrodeArray"')


def test_weight_order_does_not_affect_canonical_json():
    wf = spec.Waveform(phase_width_us=100.0)
    a = spec.StimConfig.from_map({"c": -1.0, "r1": 1.0}, waveform=wf)
    b = spec.StimConfig.from_map({"r1": 1.0, "c": -1.0}, waveform=wf)
    assert spec.to_json(a) == spec.to_json(b)


# --- union, floats, NaN ----------------------------------------------------


def test_conductivity_union_decodes_to_correct_arm():
    homog = spec.HomogeneousConductivity(sigma_S_per_m=1.5)
    lay = spec.LayeredConductivity(layers=(spec.Layer(sigma_S_per_m=1.0, thickness_um=50.0),))
    assert isinstance(spec.from_json(spec.to_json(homog)), spec.HomogeneousConductivity)
    assert isinstance(spec.from_json(spec.to_json(lay)), spec.LayeredConductivity)


@pytest.mark.parametrize("value", [0.1, 1e-10, -0.0, 1.0 / 3.0, 123456.789])
def test_floats_round_trip_losslessly(value):
    wf = spec.Waveform(phase_width_us=value)
    assert spec.from_json(spec.to_json(wf)).phase_width_us == value


@pytest.mark.parametrize("bad", [math.inf, -math.inf, math.nan])
def test_nan_and_inf_are_rejected(bad):
    wf = spec.Waveform(phase_width_us=bad)
    with pytest.raises(ValueError):
        spec.to_json(wf)


def test_missing_field_falls_back_to_default():
    # Forward-compatibility: an older payload without schema_version still decodes.
    wf = spec.from_json('{"__type__":"Waveform","phase_width_us":100.0}')
    assert wf == spec.Waveform(phase_width_us=100.0)


def test_placed_mixed_3d_array_round_trips_whole():
    # The Phase-6 stress case for the decoder: one array carrying a flat electrode
    # AND two different ElectrodeBody arms (Cylinder, Hemisphere) AND an
    # ArrayPlacement. This is what forced the multi-arm-union decode order — a
    # single payload where the tagged-dict branch must win over the union unpack.
    arr = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="F", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=12.0),
            spec.Electrode(
                id="P",
                pos_um=(30.0, 0.0, 0.0),
                shape="disk",
                size_um=0.0,
                body=spec.Cylinder(radius_um=5.0, height_um=30.0, conductive_faces="sides"),
            ),
            spec.Electrode(
                id="H",
                pos_um=(-30.0, 0.0, 0.0),
                shape="disk",
                size_um=0.0,
                body=spec.Hemisphere(radius_um=8.0),
            ),
        ),
        placement=spec.ArrayPlacement(offset_um=(100.0, 0.0, 0.0)),
    )
    back = spec.from_json(spec.to_json(arr))
    assert back == arr  # every body arm and the placement survive intact
    assert back.placement == arr.placement
    assert type(back.electrodes[1].body) is spec.Cylinder
    assert type(back.electrodes[2].body) is spec.Hemisphere
    assert spec.spec_hash(back) == spec.spec_hash(arr)  # a re-decoded array keys identically
