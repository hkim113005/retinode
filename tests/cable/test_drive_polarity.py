"""cathodic_first is a real waveform parameter: the leading edge of a biphasic pulse.

Regression for the audit finding that it was defined, hashed, serialized and
variant-tested but silently inert — apply_field_pulse hard-coded the phase order.
`leading_scale` is the pure knob it now drives; tested without NEURON."""

from dataclasses import dataclass

import pytest

from engine.cable.drive import leading_scale


@dataclass
class _WF:
    cathodic_first: bool = True


def test_cathodic_first_leads_with_the_field_as_computed():
    assert leading_scale(_WF(cathodic_first=True), monophasic=False) == 1.0


def test_anodic_first_reverses_the_leading_edge():
    # the whole point: cathodic_first=False now DOES something (anodic-first biphasic)
    assert leading_scale(_WF(cathodic_first=False), monophasic=False) == -1.0


def test_monophasic_ignores_cathodic_first():
    # one edge only: polarity is the field/weight sign, not this flag — honouring it
    # would double the weight-sign control
    assert leading_scale(_WF(cathodic_first=False), monophasic=True) == 1.0
    assert leading_scale(_WF(cathodic_first=True), monophasic=True) == 1.0


@pytest.mark.neuron
@pytest.mark.slow
def test_cathodic_and_anodic_first_give_different_thresholds(neuron_h):
    """The flag is real end to end: anodic-first biphasic activates differently from
    cathodic-first (the classic result). Also guards that the DEFAULT (cathodic-first)
    path is unchanged — every other NEURON test asserts the old numbers."""
    import dataclasses

    from app.scene import build_scene
    from engine.cable.multisite import multisite_threshold

    s = build_scene(
        layout="single", electrode_um=10.0, pitch_um=60.0,
        phase_width_us=200.0, neighbor_um=40.0, sigma_S_per_m=1.0,
    )
    target = s.patch.target()

    cath = multisite_threshold(target, s.array, s.config, s.conductivity).threshold_uA
    anodic_cfg = dataclasses.replace(
        s.config, waveform=dataclasses.replace(s.config.waveform, cathodic_first=False)
    )
    anod = multisite_threshold(target, s.array, anodic_cfg, s.conductivity).threshold_uA

    assert cath is not None and anod is not None
    assert cath != anod, "anodic-first must activate differently from cathodic-first"
