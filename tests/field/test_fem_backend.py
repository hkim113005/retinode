"""P4 S2 (fem): the DOLFINx transfer matrix, validated three ways.

(a) MMS -- a manufactured potential is recovered on the real tissue mesh to
    solver tolerance (the discretization/assembly is correct);
(b) analytical agreement -- on a homogeneous half-space, with a large enough
    domain that truncation is small, FEM A matches the analytical A (units,
    sign, magnitude, and 1/r decay all correct);
(c) current conservation -- a unit-current solve drives exactly 1 A out
    through the grounded boundary (Kirchhoff; the flux BC is right).
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

import ufl  # noqa: E402
from dolfinx import default_scalar_type, fem  # noqa: E402
from dolfinx import mesh as dmesh
from dolfinx.fem.petsc import LinearProblem  # noqa: E402
from dolfinx.io.gmsh import read_from_msh  # noqa: E402
from mpi4py import MPI  # noqa: E402

from engine.field import mesh as M  # noqa: E402
from engine.field.analytical import AnalyticalBackend  # noqa: E402
from engine.field.fem_fenicsx import FenicsxBackend, solve_transfer_matrix  # noqa: E402
from engine.spec import ElectrodeArray, HomogeneousConductivity  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem


def _centre_electrode() -> ElectrodeArray:
    return ElectrodeArray(
        electrodes=(Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )


def test_mms_recovers_a_manufactured_potential(tmp_path):
    """Impose u* = 1 + x^2 + 2y^2 + 3z^2 (so -sigma*Laplace u* = -12 sigma) as a
    Dirichlet field on the whole boundary of the *real* tissue mesh; a P2 space
    represents the quadratic exactly, so the solver must recover it."""
    arr = _centre_electrode()
    sigma_val = 0.5
    dom = M.FieldDomain(arr, HomogeneousConductivity(sigma_val), 120.0, 120.0, 6.0, 30.0)
    res = M.build_mesh(dom, str(tmp_path / "mms.msh"))
    data = read_from_msh(res.path, MPI.COMM_WORLD, gdim=3)
    msh = data.mesh  # kept in microns; MMS does not care about units

    V = fem.functionspace(msh, ("Lagrange", 2))
    u_exact = fem.Function(V)
    u_exact.interpolate(lambda x: 1.0 + x[0] ** 2 + 2.0 * x[1] ** 2 + 3.0 * x[2] ** 2)

    msh.topology.create_connectivity(msh.topology.dim - 1, msh.topology.dim)
    boundary = dmesh.exterior_facet_indices(msh.topology)
    dofs = fem.locate_dofs_topological(V, msh.topology.dim - 1, boundary)
    bc = fem.dirichletbc(u_exact, dofs)

    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    sigma = fem.Constant(msh, default_scalar_type(sigma_val))
    a = sigma * ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx
    f = fem.Constant(msh, default_scalar_type(-12.0 * sigma_val))
    L = f * v * ufl.dx
    uh = LinearProblem(
        a,
        L,
        bcs=[bc],
        petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
        petsc_options_prefix="retinode_mms_",
    ).solve()

    err = fem.form(ufl.inner(uh - u_exact, uh - u_exact) * ufl.dx)
    l2 = np.sqrt(msh.comm.allreduce(fem.assemble_scalar(err), op=MPI.SUM))
    scale = np.sqrt(
        msh.comm.allreduce(fem.assemble_scalar(fem.form(u_exact**2 * ufl.dx)), op=MPI.SUM)
    )
    assert l2 / scale < 1e-8, f"MMS relative L2 error {l2 / scale:.2e} too large"


def test_fem_matches_analytical_half_space():
    """On a homogeneous half-space, with a domain large enough that the grounded
    truncation is far from the sampled points, the FEM transfer matrix matches
    the analytical one -- validating units, sign, magnitude and 1/r decay."""
    arr = _centre_electrode()
    sigma = HomogeneousConductivity(sigma_S_per_m=1.0)
    # large domain (grounded shell ~3 mm away) so truncation error << disk/mesh error
    dom = M.FieldDomain(
        arr, sigma, half_width_um=3000.0, depth_um=3000.0, h_electrode_um=3.0, h_far_um=400.0
    )

    zs = np.array([20.0, 30.0, 40.0, 60.0, 100.0])
    q = np.column_stack([np.zeros_like(zs), np.zeros_like(zs), zs])

    a_fem = FenicsxBackend(domain=dom).transfer_matrix(arr, sigma, q)
    a_an = AnalyticalBackend().transfer_matrix(arr, sigma, q)

    assert a_fem.shape == (len(zs), 1)
    assert np.all(a_fem[:, 0] > 0)  # a current source raises the potential
    rel = np.abs(a_fem[:, 0] - a_an[:, 0]) / np.abs(a_an[:, 0])
    assert np.median(rel) < 0.06, f"median rel err {np.median(rel):.3f}"
    assert np.max(rel) < 0.10, f"max rel err {np.max(rel):.3f}"

    # 1/r decay: FEM potential ratio between z=20 and z=40 tracks analytical
    assert a_fem[0, 0] / a_fem[2, 0] == pytest.approx(a_an[0, 0] / a_an[2, 0], rel=0.05)


def test_square_electrode_solves_and_agrees_with_analytical_far_field():
    """P6 S1: a non-disk (square) electrode meshes, solves, and its *far* field
    matches analytical -- the far field is shape-agnostic (total current spread as
    a point source), so this validates the whole non-disk pipeline: mesh -> solve
    -> sample -> A in mV/uA. (The near field differs by shape; that is expected.)"""
    arr = ElectrodeArray(
        electrodes=(Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="square", size_um=12.0),)
    )
    sigma = HomogeneousConductivity(sigma_S_per_m=1.0)
    dom = M.FieldDomain(
        arr, sigma, half_width_um=3000.0, depth_um=3000.0, h_electrode_um=3.0, h_far_um=400.0
    )
    # sample well beyond the electrode (r >> 6 um) where shape washes out
    zs = np.array([40.0, 60.0, 100.0])
    q = np.column_stack([np.zeros_like(zs), np.zeros_like(zs), zs])

    a_fem = FenicsxBackend(domain=dom).transfer_matrix(arr, sigma, q)
    a_an = AnalyticalBackend().transfer_matrix(arr, sigma, q)
    assert np.all(a_fem[:, 0] > 0)
    rel = np.abs(a_fem[:, 0] - a_an[:, 0]) / np.abs(a_an[:, 0])
    assert np.max(rel) < 0.10, f"square far-field disagreement {np.max(rel):.3f}"


def test_two_electrodes_give_independent_columns():
    """Two electrodes -> two columns; column j is the field of a unit current on
    electrode j alone, so the near-diagonal dominates (each query point sits
    above its own electrode)."""
    arr = ElectrodeArray(
        electrodes=(
            Electrode(id="A", pos_um=(-40.0, 0.0, 0.0), shape="disk", size_um=10.0),
            Electrode(id="B", pos_um=(40.0, 0.0, 0.0), shape="disk", size_um=10.0),
        )
    )
    sigma = HomogeneousConductivity(sigma_S_per_m=1.0)
    dom = M.default_domain(arr, sigma, margin_factor=8.0)
    # a query point 20um above each electrode
    q = np.array([[-40.0, 0.0, 20.0], [40.0, 0.0, 20.0]])
    a = solve_transfer_matrix(dom, q, degree=1)
    assert a.shape == (2, 2)
    # point above A feels electrode A more than electrode B, and vice versa
    assert a[0, 0] > a[0, 1]
    assert a[1, 1] > a[1, 0]
    # symmetry of the geometry -> A's self-term ~ B's self-term
    assert a[0, 0] == pytest.approx(a[1, 1], rel=0.05)


def test_unit_current_is_conserved_to_ground(tmp_path):
    """A unit-current solve must drive ~1 A out through the grounded shell
    (Kirchhoff). The ground flux is the reliable check; the electrode-surface
    gradient recovery on P1 is not, so we do not assert on it."""
    arr = _centre_electrode()
    sigma_val = 1.0
    dom = M.FieldDomain(arr, HomogeneousConductivity(sigma_val), 1000.0, 1000.0, 3.0, 150.0)
    res = M.build_mesh(dom, str(tmp_path / "cons.msh"))
    data = read_from_msh(res.path, MPI.COMM_WORLD, gdim=3)
    msh, ft = data.mesh, data.facet_tags
    msh.geometry.x[:] *= 1e-6  # to metres, so current is in amps

    V = fem.functionspace(msh, ("Lagrange", 1))
    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    sigma = fem.Constant(msh, default_scalar_type(sigma_val))
    a = sigma * ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx

    msh.topology.create_connectivity(2, 3)
    gdofs = fem.locate_dofs_topological(V, 2, ft.find(res.ground_tag))
    ub = fem.Function(V)
    ub.x.array[:] = 0.0
    bc = fem.dirichletbc(ub, gdofs)

    ds = ufl.Measure("ds", domain=msh, subdomain_data=ft)
    tag = res.electrode_tags["C"]
    area = msh.comm.allreduce(
        fem.assemble_scalar(fem.form(fem.Constant(msh, 1.0) * ds(tag))), op=MPI.SUM
    )
    L = fem.Constant(msh, default_scalar_type(1.0 / area)) * v * ds(tag)
    vh = LinearProblem(
        a,
        L,
        bcs=[bc],
        petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
        petsc_options_prefix="retinode_cons_",
    ).solve()

    n = ufl.FacetNormal(msh)
    i_ground = msh.comm.allreduce(
        fem.assemble_scalar(fem.form(sigma * ufl.dot(ufl.grad(vh), n) * ds(res.ground_tag))),
        op=MPI.SUM,
    )
    assert i_ground == pytest.approx(-1.0, abs=0.02), f"ground current {i_ground:.4f} A != -1"
