"""S3: extracellular field drive + the cathodic/anodic sign chain (NEURON-marked)."""

import pytest

from engine import spec
from engine.cable.drive import run_extracellular_pulse, segment_coords

pytestmark = pytest.mark.neuron

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


@pytest.fixture(scope="module")
def cell(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()


def _scene(cell, amp_uA, weight):
    cx, cy, cz = cell._soma_center_um()
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(cx, cy, cz + 40.0), shape="disk", size_um=10.0),)
    )
    wf = spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=amp_uA)
    config = spec.StimConfig.from_map({"e": weight}, waveform=wf, distant_return=True)
    return array, config


def test_segment_coords_cover_every_segment(cell):
    coords, segs = segment_coords(cell)
    assert coords.shape == (len(segs), 3)
    assert len(segs) == sum(s.nseg for s in cell.all_sections())
    assert coords[:, 0].max() > 100.0  # the appended axon runs +x from the soma


def test_sign_chain_cathodic_depolarizes_anodic_hyperpolarizes(cell):
    # The T8 sign chain, read from the subthreshold membrane deflection so it is
    # robust (no threshold knife-edge, no biphasic/anodic-break confound).
    array, cathodic = _scene(cell, amp_uA=10.0, weight=-1.0)  # cathodic = negative
    _, anodic = _scene(cell, amp_uA=10.0, weight=1.0)  # anodic = positive
    rc = run_extracellular_pulse(cell, array, cathodic, COND, monophasic=True)
    ra = run_extracellular_pulse(cell, array, anodic, COND, monophasic=True)

    assert rc.n_spikes == 0 and ra.n_spikes == 0  # subthreshold
    assert rc.v_peak_mV > -63.0  # cathodic depolarizes above rest (~-65)
    assert ra.v_min_mV < -67.0  # anodic hyperpolarizes below rest
    assert rc.v_peak_mV > ra.v_peak_mV  # cathodic is the more depolarizing sign


def test_cathodic_pulse_fires_the_cell(cell):
    array, cathodic = _scene(cell, amp_uA=60.0, weight=-1.0)
    r = run_extracellular_pulse(cell, array, cathodic, COND, monophasic=True)
    assert r.n_spikes >= 1
    assert r.v_peak_mV > 0.0  # a real overshooting action potential
