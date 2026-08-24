"""S6d: axon-trajectory threshold spread + the activating-function diagnostic.

The perturbation geometry is pure (fast); the spread and AF wire NEURON/the field.
"""

import math

import numpy as np
import pytest

from engine import spec
from engine.cable.trajectories import perturbed_directions, trajectory_spread

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


# --- pure direction sampling (fast) --------------------------------------


def test_k1_is_the_nominal_direction():
    assert perturbed_directions((1.0, 0.0, 0.0), 1, 15.0) == [(1.0, 0.0, 0.0)]


def test_odd_k_includes_the_nominal_in_the_middle():
    dirs = perturbed_directions((1.0, 0.0, 0.0), 3, 15.0)
    assert len(dirs) == 3
    mid = dirs[1]
    assert math.isclose(mid[0], 1.0) and abs(mid[1]) < 1e-12  # angle 0 -> unchanged


def test_rotation_is_about_z_and_preserves_magnitude_and_depth():
    dirs = perturbed_directions((1.0, 0.0, -0.3), 3, 90.0)
    for dx, dy, dz in dirs:
        assert math.isclose(dz, -0.3)  # depth (z) untouched
        assert math.isclose(math.hypot(dx, dy), 1.0)  # in-plane magnitude preserved
    # +/-90 deg of +x land on +/-y
    assert math.isclose(dirs[0][1], -1.0, abs_tol=1e-9)  # -90 -> -y
    assert math.isclose(dirs[2][1], 1.0, abs_tol=1e-9)  # +90 -> +y


def test_k_must_be_positive():
    with pytest.raises(ValueError):
        perturbed_directions((1.0, 0.0, 0.0), 0, 15.0)


# --- threshold spread + AF (NEURON) --------------------------------------


@pytest.mark.neuron
def test_trajectory_spread_over_perturbed_axons(neuron_h):
    rgc = spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0))
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0), distant_return=True
    )
    s = trajectory_spread(
        rgc, array, config, COND, optic_disc=(2000.0, 0.0, -20.0), k=3, jitter_deg=20.0
    )
    assert s.n == 3
    assert s.mean_uA is not None and 1.0 < s.mean_uA < 100.0
    assert s.std_uA is not None and s.std_uA >= 0.0
    assert s.cv is not None and s.cv >= 0.0
    assert len(s.directions) == 3


@pytest.mark.neuron
def test_spread_is_real_when_the_electrode_sits_over_the_axon(neuron_h):
    # Over the AXON (not the soma), the ascending path matters: the on-axis
    # nominal path runs straight under the electrode and is most excitable;
    # swinging it off-axis raises threshold. So the spread must be non-zero.
    # This is the guard that catches axon_direction silently ceasing to thread
    # into the geometry (which would collapse every path to one threshold).
    rgc = spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0))
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(150.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0), distant_return=True
    )
    s = trajectory_spread(
        rgc, array, config, COND, optic_disc=(2000.0, 0.0, -20.0), k=5, jitter_deg=30.0
    )
    assert s.n == 5
    assert s.std_uA is not None and s.std_uA > 0.5  # a real spread, not numerical noise
    assert min(s.thresholds_uA) < max(s.thresholds_uA)


@pytest.mark.neuron
def test_activating_function_peaks_positive_under_a_cathodic_electrode(neuron_h):
    from engine.cable.channels import build_active_rgc
    from engine.cable.drive import activating_function_along_axon

    cell = build_active_rgc()  # axon runs +x from the soma at the origin
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(200.0, 0.0, 40.0), shape="disk", size_um=10.0),)
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0), distant_return=True
    )
    coords, af = activating_function_along_axon(cell, array, config, COND)
    assert coords.shape[0] == af.shape[0]
    # cathodic electrode -> Ve dips under it -> AF has a depolarizing (positive) lobe
    assert af.max() > 0.0
    # and that lobe sits near the electrode's x, not out at the far end
    peak_x = coords[int(np.argmax(af)), 0]
    assert abs(peak_x - 200.0) < 150.0
