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
