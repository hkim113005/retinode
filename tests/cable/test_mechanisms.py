"""S2a: the vendored FM mechanisms compile, load, and insert (NEURON-marked)."""

import pytest

pytestmark = pytest.mark.neuron


def test_mechanisms_load_and_insert(neuron_h):
    h = neuron_h
    sec = h.Section(name="s2a")
    sec.insert("spike")  # the FM five-channel mechanism
    sec.insert("cad")  # submembrane calcium decay
    assert h.ismembrane("spike", sec=sec)
    assert h.ismembrane("cad", sec=sec)


def test_all_five_fm_conductances_present(neuron_h):
    h = neuron_h
    sec = h.Section(name="s2a")
    sec.insert("spike")
    seg = sec(0.5)
    # Na, delayed-rectifier K, A-type K, Ca, Ca-activated K.
    for g in ("gnabar", "gkbar", "gabar", "gcabar", "gkcbar"):
        assert hasattr(seg.spike, g)
