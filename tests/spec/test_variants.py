"""Thorough coverage of every spec-object variant, plus value semantics.

The construction tests cover the common path; this exercises the field
combinations and the equality/hashability that the content cache and result
dedup will rely on.
"""

from engine import spec

# --- geometry: every shape, defaults, poly boundary ---


def test_electrode_all_shapes():
    disk = spec.Electrode(id="d", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)
    square = spec.Electrode(id="s", pos_um=(1.0, 0.0, 0.0), shape="square", size_um=8.0)
    hexa = spec.Electrode(id="h", pos_um=(2.0, 0.0, 0.0), shape="hex", size_um=12.0)
    poly = spec.Electrode(
        id="p",
        pos_um=(3.0, 0.0, 0.0),
        shape="poly",
        size_um=0.0,
        boundary_um=((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0)),
    )
    assert disk.normal == (0.0, 0.0, 1.0)      # default facing toward the retina
    assert square.boundary_um is None
    assert hexa.shape == "hex"
    assert poly.boundary_um is not None and len(poly.boundary_um) == 3


def test_electrode_array_defaults_and_order():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="z", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=5.0),
            spec.Electrode(id="a", pos_um=(9.0, 0.0, 0.0), shape="disk", size_um=5.0),
        )
    )
    assert array.frame == "patch"
    assert array.schema_version == spec.SCHEMA_VERSION
    assert array.ids() == ("z", "a")           # insertion order preserved, not sorted


# --- configuration: direct build, distant return, empty, waveform variants ---


def test_stimconfig_direct_and_distant_return():
    wf = spec.Waveform(phase_width_us=100.0)
    mono = spec.StimConfig(weights=(("c", -1.0),), waveform=wf, distant_return=True)
    assert mono.distant_return is True
    assert mono.weight_map() == {"c": -1.0}

    empty = spec.StimConfig.from_map({}, waveform=wf)
    assert empty.weights == ()
    assert empty.weight_map() == {}


def test_waveform_non_defaults():
    wf = spec.Waveform(
        phase_width_us=200.0,
        amplitude_scale_uA=3.0,
        interphase_gap_us=50.0,
        cathodic_first=False,
    )
    assert wf.kind == "biphasic"
    assert wf.cathodic_first is False
    assert wf.amplitude_scale_uA == 3.0


# --- conductivity: homogeneous, layered, anisotropy, union membership ---


def test_conductivity_variants_and_union():
    homog = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
    layered = spec.LayeredConductivity(
        layers=(
            spec.Layer(sigma_S_per_m=1.0, thickness_um=50.0),
            spec.Layer(sigma_S_per_m=0.5, thickness_um=30.0, anisotropy=(1.0, 1.0, 0.5)),
        )
    )
    # ConductivityModel is a runtime union, so isinstance works for both.
    assert isinstance(homog, spec.ConductivityModel)
    assert isinstance(layered, spec.ConductivityModel)
    assert layered.layers[1].anisotropy == (1.0, 1.0, 0.5)
    assert layered.layers[0].anisotropy is None


# --- patch: axon path, dendrite, optic disc, multiple cells ---


def test_patch_full_detail():
    target = spec.RGC(
        id="t",
        cell_type="midget_off",
        soma_um=(0.0, 0.0, -20.0),
        dendrite_diam_um=15.0,
        axon_um=((0.0, 0.0, -20.0), (50.0, 0.0, -20.0), (100.0, 0.0, -20.0)),
    )
    other = spec.RGC(id="o", cell_type="parasol_on", soma_um=(60.0, 0.0, -20.0))
    patch = spec.RetinalPatch(
        cells=(target, other),
        target_id="t",
        optic_disc_um=(4000.0, 0.0, -20.0),
    )
    assert patch.target() is target
    assert len(patch.target().axon_um) == 3
    assert other.axon_um == ()                 # default: no axon path yet


# --- study: multiple sweeps, tiers, objectives, reversed linspace ---


def test_study_variants():
    study = spec.StudyDefinition(
        sweeps=(
            spec.Sweep.linspace("array.electrodes.0.size_um", 5.0, 15.0, 3),
            spec.Sweep(path="stim.waveform.phase_width_us", values=(50.0, 100.0)),
        ),
        tier="fem",
        objectives=("sow", "charge_density"),
    )
    assert study.tier == "fem"
    assert len(study.sweeps) == 2
    assert study.sweeps[0].values == (5.0, 10.0, 15.0)


def test_sweep_linspace_reversed_and_two_points():
    assert spec.Sweep.linspace("p", 10.0, 0.0, 3).values == (10.0, 5.0, 0.0)
    assert spec.Sweep.linspace("p", 0.0, 1.0, 2).values == (0.0, 1.0)


# --- value semantics: equality + Python hashability (cache/dedup rely on these) ---


def test_equal_specs_are_equal_and_hash_equal():
    def build() -> spec.ElectrodeArray:
        return spec.ElectrodeArray(
            electrodes=(spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
        )

    a, b = build(), build()
    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1                     # value-equal specs dedup in a set


def test_specs_differing_by_one_field_are_unequal():
    base = spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)
    moved = spec.Electrode(id="c", pos_um=(1.0, 0.0, 0.0), shape="disk", size_um=10.0)
    assert base != moved
    assert len({base, moved}) == 2              # distinct values stay distinct
