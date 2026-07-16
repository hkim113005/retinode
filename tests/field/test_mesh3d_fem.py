"""P6 S2 (fem): 3D electrode bodies mesh (tissue minus body), solve, and validate.

The hemisphere is the rigorous known-answer: a hemispherical electrode of radius a
on the insulating plane produces the point-source field V = I/(2 pi sigma r) for
r >= a (mV/uA: 1e3/(2 pi sigma r)). The cylinder validates that the conductive-face
selector actually shapes the field, and DOLFINx <-> NGSolve cross-checks the 3D
mesh."""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

from engine.field import mesh as M  # noqa: E402
from engine.field.convergence import mesh_convergence  # noqa: E402
from engine.field.fem_fenicsx import (  # noqa: E402
    FenicsxBackend,
    _solve_on_mesh,
    solve_transfer_matrix,
)
from engine.spec import Cylinder, ElectrodeArray, Hemisphere, HomogeneousConductivity  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem

SIGMA = HomogeneousConductivity(sigma_S_per_m=1.0)


def _hemisphere(radius_um: float) -> ElectrodeArray:
    e = Electrode(
        id="H",
        pos_um=(0.0, 0.0, 0.0),
        shape="disk",
        size_um=0.0,
        body=Hemisphere(radius_um=radius_um),
    )
    return ElectrodeArray(electrodes=(e,))


def test_hemisphere_field_matches_the_point_source_closed_form():
    arr = _hemisphere(10.0)
    # large domain so the grounded truncation is far from the sampled near field
    dom = M.FieldDomain(arr, SIGMA, 3000.0, 3000.0, 1.5, 300.0)
    zs = np.array([20.0, 30.0, 50.0])  # r = z on the axis, all >= radius
    q = np.column_stack([np.zeros_like(zs), np.zeros_like(zs), zs])

    a_fem = FenicsxBackend(domain=dom).transfer_matrix(arr, SIGMA, q)[:, 0]
    closed = np.array([1e3 / (2 * math.pi * 1.0 * z) for z in zs])
    rel = np.abs(a_fem - closed) / closed
    assert np.max(rel) < 0.05, f"hemisphere vs closed form max err {np.max(rel):.3f}"


def test_hemisphere_field_converges_under_refinement():
    arr = _hemisphere(10.0)
    base = M.FieldDomain(arr, SIGMA, 150.0, 150.0, 4.0, 40.0)
    q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 40.0]])
    rep = mesh_convergence(base, q, factors=(1.0, 2.0, 3.0), tol=0.05, degree=1)
    assert rep.levels[-1].rel_change < rep.levels[-2].rel_change  # tightening
    assert rep.converged


def test_cylinder_conductive_faces_shape_the_field():
    # a point below the pillar tip: injecting from the tip (deep, concentrated)
    # raises the potential there more than injecting from the sides (spread out).
    q = np.array([[0.0, 0.0, 45.0]])
    ve = {}
    for faces in ("tip", "sides"):
        e = Electrode(
            id="C",
            pos_um=(0.0, 0.0, 0.0),
            shape="disk",
            size_um=0.0,
            body=Cylinder(radius_um=5.0, height_um=30.0, conductive_faces=faces),
        )
        arr = ElectrodeArray(electrodes=(e,))
        dom = M.FieldDomain(arr, SIGMA, 1000.0, 1000.0, 2.0, 150.0)
        ve[faces] = solve_transfer_matrix(dom, q, degree=1)[0, 0]
    assert ve["tip"] > 0 and ve["sides"] > 0
    assert ve["tip"] > 1.2 * ve["sides"]  # the tip clearly concentrates the field deeper


def test_dolfinx_and_ngsolve_agree_on_a_3d_hemisphere_mesh(tmp_path):
    pytest.importorskip("ngsolve")
    from engine.field.fem_ngsolve import _solve_on_mesh_ngsolve

    arr = _hemisphere(10.0)
    dom = M.FieldDomain(arr, SIGMA, 500.0, 500.0, 2.0, 80.0)
    q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 40.0], [15.0, 0.0, 25.0]])
    result = M.build_mesh(dom, str(tmp_path / "hemi.msh"))  # one mesh, both solvers
    a_dolfinx = _solve_on_mesh(result, dom, q, 1)
    a_ngsolve = _solve_on_mesh_ngsolve(result, dom, q, 1)
    rel = np.abs(a_dolfinx - a_ngsolve) / np.abs(a_dolfinx)
    assert np.max(rel) < 0.03, f"3D solver disagreement {np.max(rel):.4f}"


def test_mixed_flat_and_penetrating_array_has_independent_columns():
    # P6 S3: a flat disk + a penetrating cylinder in one array mesh together.
    flat = Electrode(id="F", pos_um=(-40.0, 0.0, 0.0), shape="disk", size_um=12.0)
    cyl = Electrode(
        id="C",
        pos_um=(40.0, 0.0, 0.0),
        shape="disk",
        size_um=0.0,
        body=Cylinder(radius_um=5.0, height_um=30.0),
    )
    arr = ElectrodeArray(electrodes=(flat, cyl))
    dom = M.FieldDomain(arr, SIGMA, 400.0, 200.0, 3.0, 60.0)
    q = np.array([[-40.0, 0.0, 20.0], [40.0, 0.0, 45.0]])  # above the flat, below the tip
    a = solve_transfer_matrix(dom, q, degree=1)
    assert a.shape == (2, 2)
    assert a[0, 0] > a[0, 1]  # the point above the flat feels the flat electrode more
    assert a[1, 1] > a[1, 0]  # the point below the tip feels the cylinder more


def test_placement_offsets_the_field_rigidly():
    # a hemisphere planted at (100, 0) matches the same hemisphere at the origin,
    # sampled the same distance above -- placement is a rigid translation.
    from engine.spec import ArrayPlacement

    base = _hemisphere(10.0)
    placed = ElectrodeArray(
        electrodes=base.electrodes, placement=ArrayPlacement(offset_um=(100.0, 0.0, 0.0))
    )
    ve_placed = solve_transfer_matrix(
        M.FieldDomain(placed, SIGMA, 500.0, 500.0, 2.0, 80.0),
        np.array([[100.0, 0.0, 25.0]]),
        degree=1,
    )[0, 0]
    ve_ref = solve_transfer_matrix(
        M.FieldDomain(base, SIGMA, 500.0, 500.0, 2.0, 80.0),
        np.array([[0.0, 0.0, 25.0]]),
        degree=1,
    )[0, 0]
    assert ve_placed == pytest.approx(ve_ref, rel=0.02)


def _write_step_cylinder(path: str, radius_um: float, height_um: float) -> None:
    import gmsh

    gmsh.initialize()
    try:
        gmsh.model.add("cyl")
        gmsh.model.occ.addCylinder(0.0, 0.0, 0.0, 0.0, 0.0, height_um, radius_um)
        gmsh.model.occ.synchronize()
        gmsh.write(path)
    finally:
        gmsh.finalize()


def test_imported_cad_cylinder_reproduces_the_primitive_field(tmp_path):
    # P6 S5: a STEP solid loaded via load_cad_body meshes, solves, and matches the
    # equivalent parametric Cylinder -- the CAD import path is correct.
    from engine.field.mesh3d import load_cad_body

    step = str(tmp_path / "cyl.step")
    _write_step_cylinder(step, 5.0, 30.0)
    cad = load_cad_body(step)
    assert cad.bounding_radius_um == pytest.approx(5.0, abs=1e-3)
    assert cad.bounding_height_um == pytest.approx(30.0, abs=1e-3)
    # exposed area (side + tip, no z=0 base) matches the primitive cylinder "all"
    assert cad.surface_area_um2 == pytest.approx(2 * math.pi * 5 * 30 + math.pi * 25, rel=1e-3)

    q = np.array([[0.0, 0.0, 45.0], [10.0, 0.0, 15.0], [0.0, 0.0, 50.0]])  # outside the body
    cad_e = Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=0.0, body=cad)
    prim_e = Electrode(
        id="C",
        pos_um=(0.0, 0.0, 0.0),
        shape="disk",
        size_um=0.0,
        body=Cylinder(radius_um=5.0, height_um=30.0),
    )
    a_cad = solve_transfer_matrix(
        M.FieldDomain(ElectrodeArray((cad_e,)), SIGMA, 1000.0, 1000.0, 2.0, 150.0), q
    )[:, 0]
    a_prim = solve_transfer_matrix(
        M.FieldDomain(ElectrodeArray((prim_e,)), SIGMA, 1000.0, 1000.0, 2.0, 150.0), q
    )[:, 0]
    assert np.max(np.abs(a_cad - a_prim) / np.abs(a_prim)) < 0.03
