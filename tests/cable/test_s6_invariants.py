"""S6 correctness invariants — cross-checks beyond the per-feature tests.

These assert properties that must hold if placement, multi-site detection, the
field coupling, and the activating function are wired correctly:

* every segment's region label names the section that segment actually lives in;
* the half-space field is invariant to an in-plane translation of cell+electrode;
* the activating function is exactly linear in stimulus polarity;
* multi-site threshold never exceeds the soma-only single-site threshold;
* initiation-site attribution agrees between the S5 and S6b code paths.
"""

import numpy as np
import pytest

from engine import spec

pytestmark = pytest.mark.neuron

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


@pytest.fixture(scope="module")
def cell(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()  # origin (0,0,0), axon +x


def _electrode_scene(pos, current, *, amp=1.0):
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=pos, shape="disk", size_um=10.0),)
    )
    config = spec.StimConfig.from_map(
        {"e": current},
        waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=amp),
        distant_return=True,
    )
    return array, config


# --- region labelling is not just the right length, but the right mapping ----


def test_segment_region_label_names_the_owning_section(cell):
    from engine.cable.drive import segment_coords, segment_regions

    _, segs = segment_coords(cell)
    labels = segment_regions(cell)
    assert len(labels) == len(segs)

    known = {"soma": cell.soma_sec, "hillock": cell.hillock, "ais": cell.ais, "axon": cell.axon}
    dend = list(cell.dendrite_secs)
    for seg, label in zip(segs, labels, strict=True):
        if label == "dendrite":
            assert any(seg.sec.same(d) for d in dend)
        else:
            assert seg.sec.same(known[label])


# --- the field only cares about relative geometry (in-plane) ------------------


def test_field_is_translation_invariant_in_plane(neuron_h):
    # Same cell + same relative electrode offset, shifted in x-y at fixed depth.
    # The z=0 half-space is homogeneous in x-y, so Ve must be identical.
    from engine.cable.channels import build_active_rgc
    from engine.cable.drive import compute_ve

    offset = (5.0, 0.0, 30.0)  # electrode relative to soma origin (30 um above)
    a = build_active_rgc(origin_um=(0.0, 0.0, -30.0), axon_direction=(1.0, 0.0, 0.0))
    b = build_active_rgc(origin_um=(150.0, -80.0, -30.0), axon_direction=(1.0, 0.0, 0.0))
    arr_a, cfg = _electrode_scene((0.0 + offset[0], 0.0 + offset[1], -30.0 + offset[2]), -1.0)
    arr_b, _ = _electrode_scene((150.0 + offset[0], -80.0 + offset[1], -30.0 + offset[2]), -1.0)

    ve_a, _ = compute_ve(a, arr_a, cfg, COND)
    ve_b, _ = compute_ve(b, arr_b, cfg, COND)
    assert ve_a.shape == ve_b.shape
    assert np.allclose(ve_a, ve_b, rtol=1e-9, atol=1e-9)
    assert np.abs(ve_a).max() > 0.0  # and the field is non-trivial


# --- the activating function is linear in the drive --------------------------


def test_activating_function_is_linear_in_polarity(cell):
    from engine.cable.drive import activating_function_along_axon

    arr_c, cfg_c = _electrode_scene((200.0, 0.0, 40.0), -1.0)  # cathodic
    arr_a, cfg_a = _electrode_scene((200.0, 0.0, 40.0), +1.0)  # anodic
    coords_c, af_c = activating_function_along_axon(cell, arr_c, cfg_c, COND)
    coords_a, af_a = activating_function_along_axon(cell, arr_a, cfg_a, COND)

    assert np.allclose(coords_c, coords_a)
    assert np.allclose(af_a, -af_c, rtol=1e-9, atol=1e-12)  # exact sign flip
    assert af_c.max() > 0.0  # cathodic depolarizes under the electrode
    assert af_a.min() < 0.0  # anodic hyperpolarizes there
    # the depolarizing lobe sits near the electrode, not at the far end
    assert abs(coords_c[int(np.argmax(af_c)), 0] - 200.0) < 150.0


# --- multi-site can only lower the threshold vs detecting at the soma alone ---


def test_multisite_threshold_at_most_single_site_soma(cell):
    import dataclasses

    from engine.cable.drive import run_extracellular_pulse
    from engine.cable.multisite import multisite_threshold
    from engine.cable.threshold import find_threshold

    cx, cy, cz = cell._soma_center_um()
    array, config = _electrode_scene((cx, cy, cz + 40.0), -1.0)

    def soma_activates(amp: float) -> bool:
        wf = dataclasses.replace(config.waveform, amplitude_scale_uA=amp)
        scaled = dataclasses.replace(config, waveform=wf)
        return run_extracellular_pulse(cell, array, scaled, COND, monophasic=True).n_spikes > 0

    soma_thr = find_threshold(
        soma_activates, amp_min=2.0, amp_max=300.0, ladder=1.5, rel_tol=0.05
    ).threshold_uA
    multi_thr = multisite_threshold(
        cell, array, config, COND, amp_min=2.0, amp_max=300.0, rel_tol=0.05
    ).threshold_uA

    assert soma_thr is not None and multi_thr is not None
    # any-compartment detection triggers no later than soma-only detection
    assert multi_thr <= soma_thr * 1.05


# --- the two initiation-site code paths agree --------------------------------


def test_initiation_site_agrees_with_multisite(cell):
    from engine.cable.initiation import initiation_site
    from engine.cable.multisite import multisite_threshold, run_multisite

    cx, cy, cz = cell._soma_center_um()
    array, config = _electrode_scene((cx, cy, cz + 40.0), -1.0)
    thr = multisite_threshold(cell, array, config, COND, amp_min=2.0, amp_max=300.0).threshold_uA
    assert thr is not None

    arr_s, cfg_s = _electrode_scene((cx, cy, cz + 40.0), -1.0, amp=thr * 1.05)
    ms = run_multisite(cell, arr_s, cfg_s, COND, dt_ms=0.005)
    init = initiation_site(cell, arr_s, cfg_s, COND, dt_ms=0.005)

    assert ms.activated and init.initiation_region is not None
    # both localize the spike to the sodium band, not the soma
    assert ms.initiation_region in ("ais", "hillock")
    assert init.initiation_region in ("ais", "hillock")
