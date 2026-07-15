"""S5: single-cell threshold reproductions vs the literature (NEURON-marked).

Density-robust checks (trends, ratios, initiation site, range) — the Wk-4
checkpoint. Absolute-value matching is deferred to the Phase-3 ex-vivo
reproductions.
"""

import pytest

from engine.validate import single_cell

pytestmark = pytest.mark.neuron


@pytest.fixture(scope="module")
def cell(neuron_h):
    from engine.cable.channels import build_active_rgc

    return build_active_rgc()


def test_threshold_rises_with_distance(cell):
    r = single_cell.threshold_rises_with_distance(cell)
    assert r.passed, r.measured


def test_axon_of_passage_is_excitable(cell):
    r = single_cell.axon_of_passage_is_excitable(cell)
    assert r.passed, r.measured


def test_spike_initiates_at_sodium_band(cell):
    r = single_cell.spike_initiates_at_sodium_band(cell)
    assert r.passed, r.measured


def test_strength_duration_decreases(cell):
    r = single_cell.strength_duration_decreases(cell)
    assert r.passed, r.measured


def test_thresholds_in_physiological_range(cell):
    r = single_cell.thresholds_in_physiological_range(cell)
    assert r.passed, r.measured


def test_cathodic_is_more_excitable_than_anodic(cell):
    r = single_cell.cathodic_is_more_excitable_than_anodic(cell)
    assert r.passed, r.measured


@pytest.mark.slow
def test_strength_duration_chronaxie(cell):
    r = single_cell.strength_duration_chronaxie(cell)
    assert r.passed, r.measured
