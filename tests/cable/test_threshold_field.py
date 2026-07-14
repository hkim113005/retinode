"""S4: real field-driven activation thresholds (NEURON-marked)."""

import pytest

from engine import spec
from engine.cable.threshold import extracellular_threshold

pytestmark = pytest.mark.neuron

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


@pytest.fixture(scope="module")
def cell(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()


def _scene(cell, height_um):
    cx, cy, cz = cell._soma_center_um()
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="e", pos_um=(cx, cy, cz + height_um), shape="disk", size_um=10.0),
        )
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0), distant_return=True
    )
    return array, config


def test_finds_a_plausible_threshold(cell):
    array, config = _scene(cell, 40.0)
    r = extracellular_threshold(cell, array, config, COND, amp_min=2.0, amp_max=300.0)
    assert r.threshold_uA is not None
    assert 5.0 < r.threshold_uA < 150.0  # plausible epiretinal range
    assert r.bracket_uA is not None and r.bracket_uA[0] <= r.threshold_uA <= r.bracket_uA[1]


def test_closer_electrode_has_lower_threshold(cell):
    near_array, near_cfg = _scene(cell, 25.0)
    far_array, far_cfg = _scene(cell, 60.0)
    near = extracellular_threshold(cell, near_array, near_cfg, COND, amp_min=2.0, amp_max=300.0)
    far = extracellular_threshold(cell, far_array, far_cfg, COND, amp_min=2.0, amp_max=300.0)
    assert near.threshold_uA < far.threshold_uA
