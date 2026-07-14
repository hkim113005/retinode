"""S2b: the RGC morphology builds from SWC with an appended axon (NEURON-marked)."""

import pytest

pytestmark = pytest.mark.neuron


@pytest.fixture(scope="module")
def rgc(neuron_h):
    from engine.cable.morphology import build_rgc

    return build_rgc()


def test_regions_present(rgc):
    r = rgc.regions()
    assert len(r["soma"]) == 1
    assert len(r["dendrite"]) > 50  # a full arbor
    assert len(r["hillock"]) == len(r["ais"]) == len(r["axon"]) == 1


def test_soma_and_ais_geometry(rgc):
    assert 20.0 < rgc.soma_sec.diam < 25.0  # ~22.75 um
    assert rgc.ais.L == 40.0 and rgc.ais.diam == 1.0  # the sodium-channel band


def test_axon_attaches_through_ais_and_hillock(rgc):
    def parent(sec):
        ps = sec.parentseg()
        return ps.sec.name().split(".")[-1] if ps else None

    assert parent(rgc.hillock).startswith("soma")
    assert parent(rgc.ais) == "hillock"
    assert parent(rgc.axon) == "ais"


def test_total_length_includes_dendrites_and_appended_axon(rgc):
    # ~3836 um of dendrite + 350 um appended (hillock 10 + AIS 40 + axon 300).
    assert rgc.total_length_um() == pytest.approx(4186.0, abs=20.0)
