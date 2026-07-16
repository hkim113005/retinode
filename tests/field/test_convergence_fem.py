"""P4 S4 (fem): the FEM field actually converges under mesh refinement.

Refines the same domain (extent fixed, so truncation is constant across levels
and only the discretization changes) and checks the transfer matrix stops moving
as the mesh sharpens -- the evidence that a reported FEM number is mesh-resolved,
not mesh-dependent."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

from engine.field.convergence import mesh_convergence  # noqa: E402
from engine.field.mesh import FieldDomain  # noqa: E402
from engine.spec import ElectrodeArray, HomogeneousConductivity  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem


def test_transfer_matrix_converges_under_refinement():
    arr = ElectrodeArray(
        electrodes=(Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    base = FieldDomain(
        arr,
        HomogeneousConductivity(1.0),
        half_width_um=150.0,
        depth_um=150.0,
        h_electrode_um=8.0,
        h_far_um=40.0,
    )
    q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 40.0], [10.0, 0.0, 25.0]])

    rep = mesh_convergence(base, q, factors=(1.0, 2.0, 3.0), tol=0.05, degree=1)

    assert len(rep.levels) == 3
    # the electrode mesh sharpens each level
    assert rep.levels[0].h_electrode_um > rep.levels[-1].h_electrode_um
    # every recorded change (after the first) is finite and bounded
    changes = [lvl.rel_change for lvl in rep.levels[1:]]
    assert all(np.isfinite(c) and c < 0.1 for c in changes)
    # the change between the two finest meshes is smaller than the previous one
    assert changes[-1] < changes[-2]
    assert rep.converged
