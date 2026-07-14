"""Fast tests for the threshold-search algorithm on synthetic curves (no NEURON)."""

import pytest

from engine.cable.threshold import find_threshold


def test_monotone_threshold():
    r = find_threshold(lambda a: a >= 5.0, amp_min=0.1, amp_max=100.0)
    assert r.threshold_uA >= 5.0  # the found threshold activates
    assert r.threshold_uA - r.tolerance_uA <= 5.0  # and is within tolerance of the edge
    assert r.activates_above is True
    assert r.upper_block_uA is None


def test_non_monotone_window_detects_upper_block():
    # Fires only in [5, 20]; blocks above — the classic upper-threshold case.
    r = find_threshold(lambda a: 5.0 <= a <= 20.0, amp_min=0.1, amp_max=100.0)
    assert r.threshold_uA == pytest.approx(5.0, abs=1.0)
    assert r.activates_above is False
    assert r.upper_block_uA is not None and r.upper_block_uA > 20.0


def test_never_activates_returns_none():
    r = find_threshold(lambda a: False, amp_min=0.1, amp_max=100.0)
    assert r.threshold_uA is None
    assert r.bracket_uA is None


def test_bracket_is_valid_and_contains_the_threshold():
    edge = 30.0

    def act(a: float) -> bool:
        return a >= edge

    r = find_threshold(act, amp_min=1.0, amp_max=200.0)
    assert r.bracket_uA is not None
    lo, hi = r.bracket_uA
    assert not act(lo) and act(hi)  # bracket straddles the edge
    assert lo <= r.threshold_uA <= hi
    assert act(r.threshold_uA)  # the found value activates


def test_first_amplitude_active_brackets_from_zero():
    # If the smallest amplitude already fires, the bracket starts at 0.
    r = find_threshold(lambda a: True, amp_min=5.0, amp_max=100.0)
    assert r.bracket_uA is not None and r.bracket_uA[0] == 0.0
    assert r.threshold_uA <= 5.0
