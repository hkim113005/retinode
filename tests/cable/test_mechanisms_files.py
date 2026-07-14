"""Fast (no-NEURON) check that the mechanism sources are vendored."""

from engine.cable import _neuron


def test_mod_files_are_vendored():
    d = _neuron.MECHANISMS_DIR
    assert (d / "spike.mod").exists()
    assert (d / "capump.mod").exists()
    assert (d / "PROVENANCE.md").exists()
