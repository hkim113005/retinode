"""P4 S4 (fast): the mesh-convergence *logic*, with an injected solver (no FEM).

The real FEM convergence run is in test_convergence_fem.py (fem)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from engine.field.convergence import mesh_convergence
from engine.field.mesh import FieldDomain
from engine.spec import ElectrodeArray, HomogeneousConductivity
from engine.spec.geometry import Electrode

ARR = ElectrodeArray(
    electrodes=(Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
COND = HomogeneousConductivity(sigma_S_per_m=1.0)
BASE = FieldDomain(
    ARR, COND, half_width_um=200.0, depth_um=200.0, h_electrode_um=8.0, h_far_um=40.0
)
Q = np.array([[0.0, 0.0, 20.0]])


def _converging_solver(dom: FieldDomain) -> np.ndarray:
    # a field whose error is proportional to the electrode mesh size, so it
    # shrinks geometrically as refined() halves h_electrode_um.
    return np.array([[5.0 + 0.1 * dom.h_electrode_um]])


def test_convergence_curve_records_levels_and_converges():
    rep = mesh_convergence(
        BASE, Q, factors=(1.0, 2.0, 4.0, 8.0), tol=0.02, solve=_converging_solver
    )
    assert len(rep.levels) == 4
    # finer meshes: h_electrode halves each level (8, 4, 2, 1)
    assert [lvl.h_electrode_um for lvl in rep.levels] == [8.0, 4.0, 2.0, 1.0]
    # first level has no predecessor to compare against
    assert math.isnan(rep.levels[0].rel_change)
    # the relative change shrinks monotonically as the mesh sharpens
    changes = [lvl.rel_change for lvl in rep.levels[1:]]
    assert all(changes[i] > changes[i + 1] for i in range(len(changes) - 1))
    assert rep.converged
    assert rep.finest.factor == 8.0


def test_non_converging_field_is_flagged():
    # error independent of mesh size -> the change between levels never shrinks
    rng_free = lambda dom: np.array([[5.0 + (dom.h_electrode_um % 3.0)]])  # noqa: E731
    rep = mesh_convergence(BASE, Q, factors=(1.0, 2.0, 4.0), tol=1e-6, solve=rng_free)
    assert not rep.converged


def test_requires_at_least_two_increasing_factors():
    with pytest.raises(ValueError, match="two refinement factors"):
        mesh_convergence(BASE, Q, factors=(1.0,), solve=_converging_solver)
    with pytest.raises(ValueError, match="strictly increasing"):
        mesh_convergence(BASE, Q, factors=(1.0, 2.0, 2.0), solve=_converging_solver)
    with pytest.raises(ValueError, match="strictly increasing"):
        mesh_convergence(BASE, Q, factors=(4.0, 2.0), solve=_converging_solver)


def test_zero_field_norm_does_not_divide_by_zero():
    rep = mesh_convergence(BASE, Q, factors=(1.0, 2.0), solve=lambda dom: np.array([[0.0]]))
    assert math.isnan(rep.levels[1].rel_change)
    assert not rep.converged
