"""S2d: the RGC fires action potentials correctly under injected current.

The Week-3 gate — sane APs above rheobase, silence below, repetitive firing
under sustained drive, and a temperature effect (NEURON-marked).
"""

import pytest

from engine.cable.simulate import run_current_step

pytestmark = pytest.mark.neuron


@pytest.fixture(scope="module")
def cell(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()  # mammalian defaults, 37 C


def test_silent_below_rheobase(cell):
    assert run_current_step(cell, 0.005, dur_ms=80, t_stop_ms=90).n_spikes == 0


def test_fires_with_overshoot_above_rheobase(cell):
    r = run_current_step(cell, 0.05, dur_ms=80, t_stop_ms=90)
    assert r.n_spikes >= 1
    assert r.v_peak_mV > 0.0  # a real overshooting AP (Na reversal +35 mV)


def test_repetitive_firing_increases_with_current(cell):
    lo = run_current_step(cell, 0.05, dur_ms=100, t_stop_ms=110).n_spikes
    hi = run_current_step(cell, 0.10, dur_ms=100, t_stop_ms=110).n_spikes
    assert lo > 1  # a train, not a single spike
    assert hi > lo  # monotonic f-I


def test_warmer_temperature_fires_faster(cell):
    # celsius is a NEURON global read live by the FM q10 scaling, so toggle it on
    # the one cell. Warmer -> faster kinetics -> higher firing rate (FM-2010).
    h = cell.h
    try:
        h.celsius = 22.0
        n_cold = run_current_step(cell, 0.05, dur_ms=80, t_stop_ms=90).n_spikes
        h.celsius = 37.0
        n_warm = run_current_step(cell, 0.05, dur_ms=80, t_stop_ms=90).n_spikes
        assert n_warm > n_cold
    finally:
        h.celsius = 37.0
