"""P4 S5 (fast): the analytical-vs-FEM regime-map *logic*, with injected solvers.

The real FEM-backed map is in test_regime_fem.py (fem)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from engine.field.mesh import FieldDomain
from engine.field.regime import analytical_error, regime_map
from engine.spec import ElectrodeArray
from engine.spec.geometry import Electrode

ARR = ElectrodeArray(
    electrodes=(Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
Q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 40.0]])
A_AN = np.array([[5.0], [3.0]])  # the (fixed) analytical field the map compares against


def _fake_analytical() -> np.ndarray:
    return A_AN


def _fake_fem(dom: FieldDomain) -> np.ndarray:
    # a field that departs from the analytical one as the layer contrast leaves 1;
    # reads the contrast off the layered conductivity the map built.
    layers = dom.conductivity.layers  # type: ignore[union-attr]
    contrast = layers[1].sigma_S_per_m / layers[0].sigma_S_per_m
    return A_AN * (1.0 + 0.5 * abs(math.log(contrast)))


def _map(contrasts, tol):
    return regime_map(
        ARR, Q, sigma1_S_per_m=1.0, contrasts=contrasts, layer_thickness_um=40.0,
        half_width_um=200.0, depth_um=100.0, h_electrode_um=4.0, h_far_um=40.0,
        tol=tol, solve_fem=_fake_fem, solve_analytical=_fake_analytical,
    )


def test_analytical_error_metric():
    a = np.array([[2.0], [4.0]])
    assert analytical_error(a, a) == 0.0
    assert analytical_error(a, np.zeros_like(a)) == pytest.approx(1.0)
    assert math.isnan(analytical_error(np.zeros_like(a), a))  # no truth to normalise by


def test_homogeneous_contrast_is_the_zero_error_anchor():
    rm = _map([1.0], tol=0.1)
    (p,) = rm.points
    assert p.contrast == 1.0
    assert p.rel_error == pytest.approx(0.0)  # contrast 1 == homogeneous -> no error
    assert p.trustworthy


def test_error_grows_with_contrast_and_flips_trustworthy():
    rm = _map([1.0, 2.0, 5.0], tol=0.3)
    errs = [p.rel_error for p in rm.points]
    assert errs[0] < errs[1] < errs[2]  # further from homogeneous -> larger error
    assert [p.trustworthy for p in rm.points] == [True, True, False]
    assert rm.trustworthy_contrasts == (1.0, 2.0)


def test_trustworthy_at_uses_the_nearest_sampled_contrast():
    rm = _map([1.0, 2.0, 5.0], tol=0.3)
    assert rm.trustworthy_at(1.1) is True  # nearest = 1.0 (trustworthy)
    assert rm.trustworthy_at(4.8) is False  # nearest = 5.0 (not)


def test_map_is_symmetric_in_log_contrast():
    # a resistive (0.5) and conductive (2.0) buried layer of equal log-contrast
    # incur equal error under the fake field
    rm = _map([0.5, 2.0], tol=1.0)
    assert rm.points[0].rel_error == pytest.approx(rm.points[1].rel_error)
