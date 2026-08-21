"""The selective operating window."""

import math

import pytest

from engine.eval import selective_operating_window


def test_sow_basic():
    sow = selective_operating_window(5.0, {"a": 10.0, "b": 8.0})
    assert sow.off_min_uA == 8.0
    assert sow.limiting_off_id == "b"
    assert sow.margin_uA == pytest.approx(3.0)
    assert sow.ratio == pytest.approx(1.6)


def test_sow_is_negative_when_an_off_target_is_more_sensitive():
    sow = selective_operating_window(10.0, {"a": 6.0})
    assert sow.margin_uA == pytest.approx(-4.0)
    assert sow.ratio == pytest.approx(0.6)


def test_no_off_targets_is_unbounded():
    sow = selective_operating_window(5.0, {})
    assert math.isinf(sow.margin_uA)
    assert math.isinf(sow.ratio)
    assert sow.limiting_off_id is None


def test_nonpositive_target_threshold_raises():
    with pytest.raises(ValueError):
        selective_operating_window(0.0, {"a": 1.0})


# --- a truncated off-target search is not the same as having no off-targets ---------


def test_no_off_targets_is_still_an_unbounded_window():
    """The genuine case: the patch has no bystanders, so nothing bounds the window."""
    w = selective_operating_window(40.0, {})
    assert math.isinf(w.off_min_uA) and math.isinf(w.ratio)
    assert w.off_min_is_lower_bound is False


def test_unreached_off_targets_bound_the_window_at_the_search_cap():
    """Bystanders that never fired below the cap used to be dropped from the dict and
    scored as 'no off-targets' — an unbounded selective window over amplitudes that
    were never probed. The honest answer is the cap, flagged as a lower bound."""
    w = selective_operating_window(40.0, {}, unreached_off_ids=("n1",), searched_max_uA=500.0)
    assert w.off_min_uA == 500.0
    assert w.off_min_is_lower_bound is True
    assert w.unreached_off_ids == ("n1",)
    assert not math.isinf(w.ratio)


def test_a_measured_minimum_is_exact_even_when_others_were_truncated():
    """An unreached bystander can only be ABOVE the cap, so it cannot lower a minimum
    that was actually measured — that bound stays exact."""
    w = selective_operating_window(
        40.0, {"n1": 90.0}, unreached_off_ids=("n2",), searched_max_uA=500.0
    )
    assert w.off_min_uA == 90.0 and w.limiting_off_id == "n1"
    assert w.off_min_is_lower_bound is False
