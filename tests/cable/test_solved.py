"""P2 S1: the solved field is computed once and reused across configs/amplitudes."""

import numpy as np
import pytest

from engine import spec
from engine.cable.solved import SolvedField
from engine.field import AnalyticalBackend, current_vector

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


# --- SolvedField.ve is just A @ I (pure, no NEURON) --------------------------


def test_ve_is_transfer_matrix_times_current_vector():
    a = np.array([[2.0, -1.0], [0.5, 3.0], [1.0, 1.0]])  # 3 segments x 2 electrodes
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="e1", pos_um=(50.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    config = spec.StimConfig.from_map(
        {"e0": -1.0, "e1": 1.0},
        waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=3.0),
    )
    sf = SolvedField(a=a, segs=[None, None, None], array=array)
    assert np.allclose(sf.ve(config), a @ current_vector(array, config))
    # amplitude just scales the same weighted sum
    doubled = spec.StimConfig.from_map(
        {"e0": -1.0, "e1": 1.0},
        waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=6.0),
    )
    assert np.allclose(sf.ve(doubled), 2.0 * sf.ve(config))


# --- a backend spy that counts transfer-matrix solves -----------------------


class CountingBackend:
    name = "counting"

    def __init__(self, inner):
        self.inner = inner
        self.calls = 0

    def transfer_matrix(self, array, conductivity, query_points_um):
        self.calls += 1
        return self.inner.transfer_matrix(array, conductivity, query_points_um)


def _scene(cell, amp=1.0):
    cx, cy, cz = cell._soma_center_um()
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(cx, cy, cz + 40.0), shape="disk", size_um=10.0),)
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0},
        waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=amp),
        distant_return=True,
    )
    return array, config


@pytest.fixture(scope="module")
def cell(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()


# --- reuse guarantees (NEURON) ----------------------------------------------


@pytest.mark.neuron
def test_solve_field_matches_compute_ve(cell):
    from engine.cable.drive import compute_ve
    from engine.cable.solved import solve_field

    array, config = _scene(cell)
    solved = solve_field(cell, array, COND)
    ve_reused = solved.ve(config)
    ve_direct, segs = compute_ve(cell, array, config, COND)
    assert np.array_equal(ve_reused, ve_direct)  # bit-identical, not merely close
    assert len(solved.segs) == len(segs)


@pytest.mark.neuron
def test_threshold_search_solves_the_field_once(cell):
    from engine.cable.multisite import multisite_threshold

    array, config = _scene(cell)
    spy = CountingBackend(AnalyticalBackend())
    thr = multisite_threshold(cell, array, config, COND, backend=spy, amp_min=2.0, amp_max=300.0)
    assert thr.threshold_uA is not None
    # a full ladder+bisect probes many amplitudes; the field is solved only once
    assert spy.calls == 1


@pytest.mark.neuron
def test_solved_field_reused_across_configurations(cell):
    from engine.cable.multisite import multisite_threshold
    from engine.cable.solved import solve_field

    array, cfg_a = _scene(cell)
    # a different waveform is a different configuration over the SAME field
    cfg_b = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=100.0), distant_return=True
    )
    spy = CountingBackend(AnalyticalBackend())
    solved = solve_field(cell, array, COND, backend=spy)  # the one and only solve
    thr_a = multisite_threshold(cell, array, cfg_a, COND, solved=solved).threshold_uA
    thr_b = multisite_threshold(cell, array, cfg_b, COND, solved=solved).threshold_uA
    assert thr_a is not None and thr_b is not None
    assert spy.calls == 1  # A solved once, reused across both configs and every amplitude
    # narrower pulse needs more current (strength-duration), a real and distinct result
    assert thr_b > thr_a


@pytest.mark.neuron
def test_presolved_field_does_not_change_the_result(cell):
    from engine.cable.multisite import run_multisite
    from engine.cable.solved import solve_field

    array, config = _scene(cell, amp=50.0)
    solved = solve_field(cell, array, COND)
    with_solved = run_multisite(cell, array, config, COND, solved=solved)
    without = run_multisite(cell, array, config, COND)  # solves internally
    assert with_solved.activated == without.activated
    assert with_solved.initiation_region == without.initiation_region
    assert with_solved.first_spike_ms == without.first_spike_ms
