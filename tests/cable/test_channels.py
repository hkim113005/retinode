"""S2c: FM channels inserted per region + temperature (NEURON-marked)."""

import pytest

pytestmark = pytest.mark.neuron


@pytest.fixture(scope="module")
def active_rgc(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()


def _gna(cell, region: str) -> float:
    return cell.regions()[region][0](0.5).spike.gnabar


def test_channels_inserted_in_every_region(active_rgc):
    h = active_rgc.h
    for secs in active_rgc.regions().values():
        for sec in secs:
            assert h.ismembrane("spike", sec=sec)
            assert h.ismembrane("cad", sec=sec)


def test_sodium_band_is_elevated(active_rgc):
    # The AIS/sodium-channel band has the highest gNa; dendrites the lowest.
    assert _gna(active_rgc, "ais") > _gna(active_rgc, "soma") > _gna(active_rgc, "dendrite")
    assert _gna(active_rgc, "ais") == pytest.approx(0.350)


def test_temperature_and_reversals(active_rgc):
    h = active_rgc.h
    assert h.celsius == 37.0
    assert h.q10_spike == 2.5
    assert active_rgc.soma_sec.ena == 35.0
    assert active_rgc.soma_sec.ek == -75.0


def test_cell_is_electrically_stable_at_rest(active_rgc):
    # With no stimulus the membrane must settle near rest and stay bounded
    # (not NaN, not runaway) — the FM resting potential is ~ -66 mV.
    h = active_rgc.h
    h.finitialize(-65)
    for _ in range(800):  # 20 ms at dt = 0.025
        h.fadvance()
    v = active_rgc.soma_sec(0.5).v
    assert -75.0 < v < -55.0
