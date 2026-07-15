"""P3 S3: Vilkhu 2025 multi-electrode current summation (NEURON)."""

import pytest

from engine.validate.nonlinearity import subthreshold_electrodes_summate


@pytest.mark.neuron
def test_subthreshold_electrodes_summate(neuron_h):
    from engine.cable.channels import build_active_rgc

    # cell at the origin, axon perpendicular to the electrode (x) axis
    cell = build_active_rgc(origin_um=(0.0, 0.0, -20.0), axon_direction=(0.0, -1.0, 0.0))
    r = subthreshold_electrodes_summate(cell)
    assert r.passed  # paired threshold falls below either single-electrode threshold
    assert r.source == "Vilkhu et al. 2025"
    assert "paired" in r.measured


@pytest.mark.neuron
@pytest.mark.slow
@pytest.mark.parametrize("spacing_um", [14.0, 24.0])
def test_summation_holds_across_spacings(neuron_h, spacing_um):
    """Robustness: current summation holds over a range of electrode spacings."""
    from engine.cable.channels import build_active_rgc

    cell = build_active_rgc(origin_um=(0.0, 0.0, -20.0), axon_direction=(0.0, -1.0, 0.0))
    r = subthreshold_electrodes_summate(cell, spacing_um=spacing_um)
    assert r.passed, r.measured
