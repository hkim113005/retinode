"""The activating function: second derivative of Ve along an axon."""

import numpy as np
import pytest

from engine.cable import activating_function


def straight_axon(n):
    return np.array([(float(i), 0.0, 0.0) for i in range(n)])


def test_linear_potential_has_zero_activating_function():
    axon = straight_axon(5)
    ve = np.array([0.0, 1.0, 2.0, 3.0, 4.0])  # linear in x
    af = activating_function(axon, ve)
    assert np.allclose(af, 0.0)


def test_quadratic_potential_gives_constant_second_derivative():
    axon = straight_axon(4)  # spacing 1
    ve = np.array([0.0, 1.0, 4.0, 9.0])  # x^2
    af = activating_function(axon, ve)
    assert af[0] == 0.0 and af[-1] == 0.0  # endpoints undefined -> 0
    assert np.allclose(af[1:-1], 2.0)  # d2/dx2 of x^2 is 2


def test_handles_non_uniform_spacing():
    # s = [0, 1, 3], Ve = s^2 -> second derivative is still 2 at the interior point.
    axon = np.array([(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (3.0, 0.0, 0.0)])
    ve = np.array([0.0, 1.0, 9.0])
    af = activating_function(axon, ve)
    assert af[1] == pytest.approx(2.0)


def test_short_axon_returns_zeros():
    assert np.allclose(activating_function(straight_axon(2), np.array([0.0, 1.0])), 0.0)


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        activating_function(straight_axon(4), np.array([0.0, 1.0, 2.0]))
