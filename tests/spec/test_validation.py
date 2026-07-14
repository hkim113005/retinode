"""Every validation rule: a spec that trips it, and a clean spec that doesn't.

The Problem `code` is the contract tests key on, so each rule is checked by
code rather than by message text.
"""

import pytest

from engine import spec


def codes(problems) -> set[str]:
    return {p.code for p in problems}


# --- a known-good scene, reused as the "clean" baseline --------------------


def valid_scene():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="r1", pos_um=(30.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    config = spec.StimConfig.from_map(
        {"c": -1.0, "r1": 1.0}, waveform=spec.Waveform(phase_width_us=100.0)
    )
    cond = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
    patch = spec.RetinalPatch(
        cells=(spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),),
        target_id="t",
    )
    return array, config, cond, patch


def test_valid_scene_has_no_problems():
    array, config, cond, patch = valid_scene()
    problems = spec.validate_scene(array, config, cond, patch)
    assert problems == []
    assert not spec.has_errors(problems)


def test_unknown_object_type_raises():
    with pytest.raises(TypeError):
        spec.validate(object())


# --- geometry --------------------------------------------------------------


def test_empty_array():
    assert "empty-array" in codes(spec.validate(spec.ElectrodeArray(electrodes=())))


def test_duplicate_electrode_id():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="c", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="c", pos_um=(50.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    assert "duplicate-electrode-id" in codes(spec.validate(array))


def test_electrode_overlap_flagged_and_touching_is_ok():
    overlapping = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="a", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(
                id="b", pos_um=(8.0, 0.0, 0.0), shape="disk", size_um=10.0
            ),  # centers 8 < 10
        )
    )
    assert "electrode-overlap" in codes(spec.validate(overlapping))

    spaced = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="a", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(
                id="b", pos_um=(12.0, 0.0, 0.0), shape="disk", size_um=10.0
            ),  # centers 12 > 10
        )
    )
    assert "electrode-overlap" not in codes(spec.validate(spaced))


def test_poly_missing_boundary():
    e = spec.Electrode(id="p", pos_um=(0.0, 0.0, 0.0), shape="poly", size_um=0.0)
    assert "poly-missing-boundary" in codes(spec.validate(e))


def test_negative_electrode_size():
    e = spec.Electrode(id="n", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=-1.0)
    assert "negative-electrode-size" in codes(spec.validate(e))


# --- configuration ---------------------------------------------------------


def test_charge_imbalance_on_array_but_ok_when_distant():
    wf = spec.Waveform(phase_width_us=100.0)
    imbalanced = spec.StimConfig.from_map({"c": -1.0, "r1": 0.5}, waveform=wf)  # sums to -0.5
    assert "charge-imbalance" in codes(spec.validate(imbalanced))

    # Same weights, but monopolar: the far ground carries the balance.
    monopolar = spec.StimConfig(
        weights=(("c", -1.0), ("r1", 0.5)), waveform=wf, distant_return=True
    )
    assert "charge-imbalance" not in codes(spec.validate(monopolar))


def test_empty_config():
    cfg = spec.StimConfig.from_map({}, waveform=spec.Waveform(phase_width_us=100.0))
    assert "empty-config" in codes(spec.validate(cfg))


def test_duplicate_weight_id():
    cfg = spec.StimConfig(
        weights=(("c", -1.0), ("c", 1.0)),
        waveform=spec.Waveform(phase_width_us=100.0),
    )
    assert "duplicate-weight-id" in codes(spec.validate(cfg))


def test_waveform_rules():
    assert "waveform-nonpositive-phase" in codes(spec.validate(spec.Waveform(phase_width_us=0.0)))
    assert "waveform-negative-gap" in codes(
        spec.validate(spec.Waveform(phase_width_us=100.0, interphase_gap_us=-1.0))
    )
    # zero amplitude is a warning, not an error
    problems = spec.validate(spec.Waveform(phase_width_us=100.0, amplitude_scale_uA=0.0))
    assert "waveform-zero-amplitude" in codes(problems)
    assert not spec.has_errors(problems)


# --- conductivity ----------------------------------------------------------


def test_homogeneous_nonpositive_conductivity():
    assert "nonpositive-conductivity" in codes(
        spec.validate(spec.HomogeneousConductivity(sigma_S_per_m=0.0))
    )


def test_layered_rules():
    assert "empty-conductivity" in codes(spec.validate(spec.LayeredConductivity(layers=())))
    bad = spec.LayeredConductivity(
        layers=(
            spec.Layer(sigma_S_per_m=-1.0, thickness_um=0.0),
            spec.Layer(sigma_S_per_m=1.0, thickness_um=10.0, anisotropy=(1.0, 0.0, 1.0)),
        )
    )
    found = codes(spec.validate(bad))
    assert {"nonpositive-conductivity", "nonpositive-thickness", "nonpositive-anisotropy"} <= found


# --- patch -----------------------------------------------------------------


def test_empty_patch():
    assert "empty-patch" in codes(spec.validate(spec.RetinalPatch(cells=(), target_id="t")))


def test_no_target():
    patch = spec.RetinalPatch(
        cells=(spec.RGC(id="a", cell_type="x", soma_um=(0.0, 0.0, 0.0)),),
        target_id="missing",
    )
    assert "no-target" in codes(spec.validate(patch))


def test_duplicate_cell_id():
    patch = spec.RetinalPatch(
        cells=(
            spec.RGC(id="a", cell_type="x", soma_um=(0.0, 0.0, 0.0)),
            spec.RGC(id="a", cell_type="y", soma_um=(1.0, 0.0, 0.0)),
        ),
        target_id="a",
    )
    assert "duplicate-cell-id" in codes(spec.validate(patch))


# --- study -----------------------------------------------------------------


def test_study_rules():
    assert "empty-study" in codes(spec.validate(spec.StudyDefinition(sweeps=())))
    study = spec.StudyDefinition(sweeps=(spec.Sweep(path="", values=()),))
    found = codes(spec.validate(study))
    assert {"empty-sweep-path", "empty-sweep-values"} <= found


# --- cross-object (scene) --------------------------------------------------


def test_unknown_electrode_in_config():
    array, _, cond, patch = valid_scene()
    config = spec.StimConfig.from_map(
        {"c": -1.0, "ghost": 1.0}, waveform=spec.Waveform(phase_width_us=100.0)
    )
    assert "unknown-electrode" in codes(spec.validate_scene(array, config, cond, patch))


def test_layers_do_not_span_depth():
    array, config, _, patch = valid_scene()  # patch reaches 20 um deep
    too_thin = spec.LayeredConductivity(layers=(spec.Layer(sigma_S_per_m=1.0, thickness_um=10.0),))
    assert "layers-do-not-span-depth" in codes(spec.validate_scene(array, config, too_thin, patch))

    deep_enough = spec.LayeredConductivity(
        layers=(spec.Layer(sigma_S_per_m=1.0, thickness_um=50.0),)
    )
    assert "layers-do-not-span-depth" not in codes(
        spec.validate_scene(array, config, deep_enough, patch)
    )


def test_poly_electrode_overlap_uses_boundary_radius():
    # Polygon electrodes have no size_um, so overlap uses the boundary-derived
    # radius (max distance from center to a vertex). Both here have radius 10
    # with centers 12 apart, so they overlap.
    a_boundary = ((10.0, 0.0, 0.0), (-10.0, 0.0, 0.0), (0.0, 10.0, 0.0))
    b_boundary = ((22.0, 0.0, 0.0), (2.0, 0.0, 0.0), (12.0, 10.0, 0.0))
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(
                id="a", pos_um=(0.0, 0.0, 0.0), shape="poly", size_um=0.0, boundary_um=a_boundary
            ),
            spec.Electrode(
                id="b", pos_um=(12.0, 0.0, 0.0), shape="poly", size_um=0.0, boundary_um=b_boundary
            ),
        )
    )
    assert "electrode-overlap" in codes(spec.validate(array))
