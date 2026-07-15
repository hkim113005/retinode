"""S7: the fixed evaluator.

Scoring logic is exercised without NEURON via an injected thresholds provider;
one neuron-marked test runs the whole pipeline end-to-end on a real patch.
"""

import pytest

from engine import spec
from engine.cable.population import PopulationThresholds
from engine.eval import (
    EVALUATOR_VERSION,
    OffTargetSet,
    SafetyLimits,
    evaluate,
    max_safe_amplitude_uA,
    require_same_offtarget,
)
from engine.store.keys import result_key

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
ARR = spec.ElectrodeArray(
    electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
CFG = spec.StimConfig.from_map({"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0))


def _patch():
    return spec.RetinalPatch(
        cells=(
            spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
            spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
        ),
        target_id="t",
        optic_disc_um=(2000.0, 0.0, -20.0),
    )


def _provider(target_uA, off):
    """A thresholds provider that returns fixed values (no NEURON)."""

    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None):
        return PopulationThresholds(patch.target_id, target_uA, dict(off))

    return provider


# --- the operating window: selective vs safety limited -----------------------


def test_window_limited_by_off_target_when_safety_ceiling_is_higher():
    # ceiling is generous; the off-target threshold is the binding cap.
    ceiling = max_safe_amplitude_uA(ARR, CFG)
    off_min = ceiling * 0.5  # off-target fires below the safety ceiling
    r = evaluate(
        _patch(), ARR, CFG, COND, thresholds_provider=_provider(off_min * 0.4, {"n1": off_min})
    )
    assert r.activated
    assert r.window is not None and r.window.limiting == "off_target"
    assert r.window.window_hi_uA == pytest.approx(off_min)
    assert r.window.is_usable  # target (0.4*off_min) < off_min
    assert r.sow is not None and r.sow.limiting_off_id == "n1"


def test_window_limited_by_safety_when_ceiling_is_lower():
    ceiling = max_safe_amplitude_uA(ARR, CFG)
    off_min = ceiling * 2.0  # off-target above the ceiling -> safety binds
    r = evaluate(
        _patch(), ARR, CFG, COND, thresholds_provider=_provider(ceiling * 0.5, {"n1": off_min})
    )
    assert r.window is not None
    assert r.window.limiting == "safety"
    assert r.window.window_hi_uA == pytest.approx(ceiling)
    assert r.window.safety_ceiling_uA == pytest.approx(ceiling)


def test_no_off_targets_leaves_selective_hi_unbounded():
    r = evaluate(_patch(), ARR, CFG, COND, thresholds_provider=_provider(5.0, {}))
    assert r.sow is not None and r.sow.off_min_uA == float("inf")
    # with no off-target, only safety can cap the window
    assert r.window is not None and r.window.limiting in ("safety", "none")


def test_target_that_never_fires_has_no_window():
    r = evaluate(_patch(), ARR, CFG, COND, thresholds_provider=_provider(None, {"n1": 20.0}))
    assert not r.activated
    assert r.sow is None and r.window is None and r.safety_at_target is None


# --- provenance --------------------------------------------------------------


def test_result_carries_matching_key_and_hashes():
    off = OffTargetSet()
    r = evaluate(
        _patch(), ARR, CFG, COND, off_target_set=off, thresholds_provider=_provider(8.0, {})
    )
    expected = result_key(
        ARR,
        COND,
        CFG,
        _patch(),
        off,
        backend_name="analytical",
        evaluator_version=EVALUATOR_VERSION,
    )
    assert r.result_key == expected
    assert r.evaluator_version == EVALUATOR_VERSION
    assert r.safety_at_target is not None and r.safety_at_target.safe


def test_refuses_to_compare_across_off_target_sets():
    p = _patch()
    a = evaluate(
        p, ARR, CFG, COND, off_target_set=OffTargetSet(), thresholds_provider=_provider(8.0, {})
    )
    b = evaluate(
        p,
        ARR,
        CFG,
        COND,
        off_target_set=OffTargetSet(soma_radius_um=80.0),
        thresholds_provider=_provider(8.0, {}),
    )
    assert not a.same_offtarget(b)
    with pytest.raises(ValueError, match="off-target"):
        require_same_offtarget(a, b)
    require_same_offtarget(a, a)  # same set is fine


# --- safety ceiling round-trips against assess_safety ------------------------


def test_ceiling_is_the_safety_boundary():
    from engine.eval import assess_safety

    limits = SafetyLimits(shannon_k=1.5)
    ceiling = max_safe_amplitude_uA(ARR, CFG, limits)
    just_under = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=ceiling * 0.99)
    )
    just_over = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=ceiling * 1.01)
    )
    assert assess_safety(ARR, just_under, limits).safe
    assert not assess_safety(ARR, just_over, limits).safe


def test_material_limit_can_bind_before_shannon():
    tight = SafetyLimits(shannon_k=1.5, material_charge_density_uC_per_cm2=1.0)
    loose = SafetyLimits(shannon_k=1.5, material_charge_density_uC_per_cm2=None)
    assert max_safe_amplitude_uA(ARR, CFG, tight) < max_safe_amplitude_uA(ARR, CFG, loose)


# --- end to end (NEURON) -----------------------------------------------------


@pytest.mark.neuron
def test_evaluate_end_to_end(neuron_h):
    patch = spec.RetinalPatch(
        cells=(
            spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
            spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
            spec.RGC(id="far", cell_type="parasol_on", soma_um=(500.0, 0.0, -20.0)),
        ),
        target_id="t",
        optic_disc_um=(2000.0, 0.0, -20.0),
    )
    r = evaluate(patch, ARR, CFG, COND)  # real population_thresholds
    assert r.activated
    assert r.thresholds.target_threshold_uA is not None
    assert r.sow is not None and r.sow.ratio > 1.0  # target more excitable than off-targets
    assert r.window is not None and r.window.target_uA == r.thresholds.target_threshold_uA
    assert r.safety_at_target is not None
    assert r.result_key == result_key(
        ARR,
        COND,
        CFG,
        patch,
        OffTargetSet(),
        backend_name="analytical",
        evaluator_version=EVALUATOR_VERSION,
    )
