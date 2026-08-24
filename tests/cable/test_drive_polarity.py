"""cathodic_first is a real waveform parameter: the leading edge of a biphasic pulse.

Regression for the audit finding that it was defined, hashed, serialized and
variant-tested but silently inert, because apply_field_pulse hard-coded the phase order.
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
    # one edge only: polarity is the field/weight sign, not this flag. Honouring it
    # would double the weight-sign control
    assert leading_scale(_WF(cathodic_first=False), monophasic=True) == 1.0
    assert leading_scale(_WF(cathodic_first=True), monophasic=True) == 1.0


@pytest.mark.neuron
@pytest.mark.slow
def test_cathodic_first_changes_where_the_spike_initiates(neuron_h):
    """The flag is real end to end: reversing a biphasic pulse's order changes the
    outcome. At a fixed supra-threshold amplitude the two orders initiate the spike in
    a different region (soma for cathodic-first, AIS for anodic-first), the
    axon-avoidance-relevant observable.

    Note it is the initiation *site/timing* that differs, not the threshold amplitude:
    at these phase widths each phase acts near-independently, so the depolarizing phase
    reaches threshold at the same amplitude regardless of order (verified: both land
    on the same search bracket). cathodic_first is only meaningful for BIPHASIC pulses;
    the tool's threshold search defaults to monophasic, where `leading_scale` ignores
    it (one edge, polarity is the weight sign). The DEFAULT cathodic-first path is
    unchanged: every other NEURON test asserts the old numbers, and they pass."""
    import dataclasses

    from app.scene import build_scene
    from engine.cable.multisite import run_multisite
    from engine.cable.placement import place_cell
    from engine.cable.solved import solve_field
    from engine.field import AnalyticalBackend

    s = build_scene(
        layout="single", electrode_um=10.0, pitch_um=100.0, phase_width_us=100.0,
        neighbor_um=40.0, sigma_S_per_m=1.0,
    )
    target = place_cell(s.patch.target(), optic_disc=s.patch.optic_disc_um)
    solved = solve_field(target, s.array, s.conductivity, AnalyticalBackend())

    def outcome(cathodic_first: bool):
        cfg = dataclasses.replace(
            s.config,
            waveform=dataclasses.replace(
                s.config.waveform, amplitude_scale_uA=20.0, cathodic_first=cathodic_first
            ),
        )
        r = run_multisite(target, s.array, cfg, s.conductivity, solved=solved, monophasic=False)
        return (r.activated, r.initiation_region, r.first_spike_ms)

    cath, anod = outcome(True), outcome(False)
    assert cath[0] and anod[0], "both orders should fire at this supra-threshold amplitude"
    assert cath != anod, "reversing the biphasic order must change the outcome"
    assert cath[1] != anod[1], "the initiation region should differ (soma vs AIS)"
