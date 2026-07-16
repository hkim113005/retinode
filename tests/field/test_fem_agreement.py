"""P4 S5 (fem): DOLFINx and NGSolve agree on the same mesh.

The "confirmed by a second backend" done-when (Phase-4 D2). Two independent FEM
libraries solve the *same* gmsh mesh with the same BCs and unit chain; a bug in
either one's assembly, boundary handling, or unit conversion would break the
agreement. Both read one built mesh (``_solve_on_mesh*`` share the MeshResult), so
this isolates solver differences from meshing differences -- what is left is pure
numerics, and it is sub-percent.
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("ngsolve")
pytest.importorskip("gmsh")

from engine.field import mesh as M  # noqa: E402
from engine.field.fem_fenicsx import _solve_on_mesh  # noqa: E402
from engine.field.fem_ngsolve import _solve_on_mesh_ngsolve  # noqa: E402
from engine.spec import ElectrodeArray, HomogeneousConductivity, LayeredConductivity  # noqa: E402
from engine.spec.conductivity import Layer  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem


def _bipolar_array() -> ElectrodeArray:
    return ElectrodeArray(
        electrodes=(
            Electrode(id="A", pos_um=(-30.0, 0.0, 0.0), shape="disk", size_um=10.0),
            Electrode(id="B", pos_um=(30.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )


def _agree(dom: M.FieldDomain, tmp_path) -> None:
    q = np.array([[-30.0, 0.0, 20.0], [30.0, 0.0, 20.0], [0.0, 0.0, 30.0]])
    result = M.build_mesh(dom, str(tmp_path / "agree.msh"))  # one mesh, both solvers
    a_dolfinx = _solve_on_mesh(result, dom, q, 1)
    a_ngsolve = _solve_on_mesh_ngsolve(result, dom, q, 1)
    assert a_dolfinx.shape == a_ngsolve.shape == (3, 2)
    rel = np.abs(a_dolfinx - a_ngsolve) / np.abs(a_dolfinx)
    assert np.max(rel) < 0.03, f"max solver disagreement {np.max(rel):.4f}"
    assert np.median(rel) < 0.01


def test_dolfinx_and_ngsolve_agree_on_a_homogeneous_half_space(tmp_path):
    arr = _bipolar_array()
    dom = M.FieldDomain(arr, HomogeneousConductivity(1.0), 400.0, 400.0, 4.0, 60.0)
    _agree(dom, tmp_path)


def test_dolfinx_and_ngsolve_agree_on_a_layered_medium(tmp_path):
    arr = _bipolar_array()
    cond = LayeredConductivity(layers=(Layer(1.0, 40.0), Layer(0.3, 60.0)))
    dom = M.FieldDomain(arr, cond, 400.0, 100.0, 4.0, 60.0)
    _agree(dom, tmp_path)
