"""Structural invariants — the contract the whole system forks from.

These lock the *shape* of the spec, so any drift (a renamed field, a stray
current on geometry) fails in CI instead of silently invalidating cached
results and past comparisons downstream.
"""

from dataclasses import fields

from engine import spec

# Locking each object's exact field set makes "the spec is frozen" enforceable:
# adding, removing, or renaming a field is now a deliberate, reviewed event.
EXPECTED_FIELDS = {
    spec.Electrode: {"id", "pos_um", "shape", "size_um", "normal", "boundary_um", "body"},
    spec.ElectrodeArray: {"electrodes", "frame", "placement", "schema_version"},
    spec.Waveform: {
        "phase_width_us",
        "amplitude_scale_uA",
        "interphase_gap_us",
        "cathodic_first",
        "kind",
    },
    spec.StimConfig: {"weights", "waveform", "distant_return", "schema_version"},
    spec.Layer: {"sigma_S_per_m", "thickness_um", "anisotropy"},
    spec.HomogeneousConductivity: {"sigma_S_per_m", "schema_version"},
    spec.LayeredConductivity: {"layers", "schema_version"},
    spec.RGC: {"id", "cell_type", "soma_um", "dendrite_diam_um", "axon_um"},
    spec.RetinalPatch: {"cells", "target_id", "optic_disc_um", "frame", "schema_version"},
    spec.Sweep: {"path", "values"},
    spec.StudyDefinition: {"sweeps", "tier", "objectives", "schema_version"},
}


def test_spec_shapes_are_locked():
    for cls, expected in EXPECTED_FIELDS.items():
        assert {f.name for f in fields(cls)} == expected, cls.__name__


def test_geometry_carries_no_current():
    # The structural half of the geometry/configuration wall: geometry cannot
    # express current, so the cheap/expensive boundary cannot blur.
    geometry = {f.name for f in fields(spec.Electrode)}
    geometry |= {f.name for f in fields(spec.ElectrodeArray)}
    assert not (geometry & {"current", "weight", "weights", "amplitude", "amplitude_scale_uA"})


def test_configuration_carries_no_geometry():
    configuration = {f.name for f in fields(spec.StimConfig)}
    configuration |= {f.name for f in fields(spec.Waveform)}
    assert not (configuration & {"pos_um", "position", "shape", "size_um", "normal"})


def test_top_level_objects_have_schema_version():
    for cls in (
        spec.ElectrodeArray,
        spec.StimConfig,
        spec.HomogeneousConductivity,
        spec.LayeredConductivity,
        spec.RetinalPatch,
        spec.StudyDefinition,
    ):
        assert "schema_version" in {f.name for f in fields(cls)}


def test_public_exports_are_importable():
    for name in spec.__all__:
        assert hasattr(spec, name), name
