"""Charge and Shannon-safety arithmetic."""

import math

import pytest

from engine import spec
from engine.eval import (
    SafetyLimits,
    assess_safety,
    charge_per_phase_uC,
    electrode_area_um2,
)


def array_with(shape="disk", size=10.0):
    return spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape=shape, size_um=size),)
    )


def config(amplitude_uA=100.0, phase_us=100.0, weight=1.0):
    wf = spec.Waveform(phase_width_us=phase_us, amplitude_scale_uA=amplitude_uA)
    return spec.StimConfig.from_map({"e": weight}, waveform=wf, distant_return=True)


def test_charge_per_phase_units():
    # 100 uA * 100 us = 0.01 uC.
    assert charge_per_phase_uC(100.0, 100.0) == pytest.approx(0.01)
    assert charge_per_phase_uC(-100.0, 100.0) == pytest.approx(0.01)  # magnitude


def test_electrode_area_by_shape():
    assert electrode_area_um2(
        spec.Electrode(id="d", pos_um=(0, 0, 0), shape="disk", size_um=10.0)
    ) == pytest.approx(math.pi * 25.0)
    assert electrode_area_um2(
        spec.Electrode(id="s", pos_um=(0, 0, 0), shape="square", size_um=10.0)
    ) == pytest.approx(100.0)
    assert electrode_area_um2(
        spec.Electrode(id="h", pos_um=(0, 0, 0), shape="hex", size_um=10.0)
    ) == pytest.approx((math.sqrt(3) / 2) * 100.0)
    poly = spec.Electrode(
        id="p",
        pos_um=(0, 0, 0),
        shape="poly",
        size_um=0.0,
        boundary_um=((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (0.0, 10.0, 0.0)),
    )
    assert electrode_area_um2(poly) == pytest.approx(100.0)  # shoelace of a 10x10 square


def test_high_charge_density_is_flagged_unsafe():
    report = assess_safety(array_with(size=10.0), config(amplitude_uA=100.0))
    assert not report.safe
    assert report.per_electrode[0].exceeds_shannon


def test_low_charge_density_is_safe():
    # Large electrode, small current -> well under the Shannon boundary.
    report = assess_safety(array_with(size=200.0), config(amplitude_uA=10.0))
    assert report.safe
    assert report.per_electrode[0].shannon_k < 1.5


def test_material_limit_can_fail_an_otherwise_safe_config():
    array, cfg = array_with(size=200.0), config(amplitude_uA=10.0)
    safe = assess_safety(array, cfg)
    assert safe.safe
    strict = assess_safety(array, cfg, SafetyLimits(material_charge_density_uC_per_cm2=1.0))
    assert not strict.safe
    assert strict.per_electrode[0].exceeds_material


def test_inactive_electrodes_are_skipped():
    array = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="on", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),
            spec.Electrode(id="off", pos_um=(50.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    wf = spec.Waveform(phase_width_us=100.0, amplitude_scale_uA=10.0)
    cfg = spec.StimConfig.from_map({"on": 1.0}, waveform=wf, distant_return=True)
    report = assess_safety(array, cfg)
    assert [e.electrode_id for e in report.per_electrode] == ["on"]
