"""P3 S2: Vilkhu 2021 confined-return axon avoidance (fast AF + NEURON threshold)."""

import pytest

from engine.validate.axon_avoidance import (
    confined_return_avoids_axon_of_passage,
    confined_return_flattens_axon_af,
)


def test_confined_return_flattens_axon_af():
    r = confined_return_flattens_axon_af()
    assert r.passed  # confined peak activating function is below monopolar
    assert r.source == "Vilkhu et al. 2021"
    assert "lower" in r.measured


@pytest.mark.neuron
def test_confined_return_avoids_axon_of_passage(neuron_h):
    from engine.cable.channels import build_active_rgc

    # a cell whose axon crosses offset under the array (soma far to the side)
    cell = build_active_rgc(origin_um=(-200.0, 40.0, -20.0), axon_direction=(1.0, 0.0, 0.0))
    r = confined_return_avoids_axon_of_passage(cell)
    assert r.passed  # the confined pattern raises (or removes) the axon-of-passage threshold
    assert "monopolar" in r.measured and "confined" in r.measured


@pytest.mark.neuron
@pytest.mark.slow
@pytest.mark.parametrize("offset_um", [30.0, 50.0])
def test_axon_avoidance_holds_across_offsets(neuron_h, offset_um):
    """Robustness: avoidance is not a single lucky offset — it holds over a range."""
    from engine.cable.channels import build_active_rgc

    cell = build_active_rgc(origin_um=(-200.0, offset_um, -20.0), axon_direction=(1.0, 0.0, 0.0))
    r = confined_return_avoids_axon_of_passage(cell)
    assert r.passed, r.measured
