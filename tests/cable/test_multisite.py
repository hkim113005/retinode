"""S6b: multi-site activation — a spike at any compartment (NEURON-marked)."""

import pytest

from engine import spec
from engine.cable.multisite import multisite_threshold, run_multisite, segment_regions

pytestmark = pytest.mark.neuron

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


@pytest.fixture(scope="module")
def cell(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()


def _scene(cell, dx, amp):
    cx, cy, cz = cell._soma_center_um()
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="e", pos_um=(cx + dx, cy, cz + 40.0), shape="disk", size_um=10.0),
        )
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0},
        waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=amp),
        distant_return=True,
    )
    return array, config


@pytest.fixture(scope="module")
def soma_threshold(cell):
    array, config = _scene(cell, 0.0, 1.0)
    return multisite_threshold(cell, array, config, COND, amp_min=2.0, amp_max=300.0).threshold_uA


def test_segment_regions_align_with_segments(cell):
    from engine.cable.drive import segment_coords

    _, segs = segment_coords(cell)
    assert len(segment_regions(cell)) == len(segs)


def test_multisite_activation_and_ais_initiation(cell, soma_threshold):
    array, config = _scene(cell, 0.0, soma_threshold * 1.03)
    r = run_multisite(cell, array, config, COND, dt_ms=0.005)
    assert r.activated
    assert r.initiation_region in ("ais", "hillock")  # spike starts at the Na band
    assert r.n_active_segments > 5  # and propagates


def test_initiation_site_follows_the_electrode(cell, soma_threshold):
    # Over the distal axon, the spike initiates at the axon — the any-compartment
    # property that makes an off-target axon of passage first-class.
    array, config = _scene(cell, 200.0, soma_threshold * 1.03)
    r = run_multisite(cell, array, config, COND, dt_ms=0.005)
    assert r.activated
    assert r.initiation_region == "axon"


def test_subthreshold_is_not_activated(cell, soma_threshold):
    array, config = _scene(cell, 0.0, soma_threshold * 0.5)
    assert not run_multisite(cell, array, config, COND).activated
