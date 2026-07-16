"""P4 S3 (fem): layered conductivity -- the value-add the analytical tier rejects.

Two validations:

    (a) two-layer closed form -- for a current source on the insulating surface
        of a two-layer half-space, the in-layer potential has a classic
        image-series closed form; FEM must match it (and must differ from the
        homogeneous field by the physically correct amount);
    (b) layered MMS -- a flux-continuous, piecewise-linear exact solution across
        the sigma jump is recovered to machine precision, confirming the
        interface is handled (V- and sigma dV/dn-continuous).
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
from engine.field.fem_fenicsx import _build_sigma, solve_transfer_matrix  # noqa: E402
from engine.spec import (  # noqa: E402
    ElectrodeArray,
    HomogeneousConductivity,
    LayeredConductivity,
)
from engine.spec.conductivity import Layer  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem


def _centre_electrode() -> ElectrodeArray:
    return ElectrodeArray(
        electrodes=(Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )


def _two_layer_surface_source(
    r_um: float, z_um: float, sigma1: float, sigma2: float, h_um: float, n_terms: int = 400
) -> float:
    """In-layer potential (mV/uA) at (r, z), 0 <= z <= h, for a unit current
    source on the insulating surface of a two-layer half-space: layer 1 is
    0<z<h with sigma1, layer 2 is z>h with sigma2. Method-of-images series with
    reflection coefficient k=(sigma1-sigma2)/(sigma1+sigma2); the 1e3/(2 pi s1)
    prefactor and the surface image-doubling match analytical.py's units."""
    k = (sigma1 - sigma2) / (sigma1 + sigma2)
    total = 1.0 / np.hypot(r_um, z_um)
    for n in range(1, n_terms + 1):
        total += k**n * (
            1.0 / np.hypot(r_um, z_um - 2 * n * h_um) + 1.0 / np.hypot(r_um, z_um + 2 * n * h_um)
        )
    return float(1.0e3 / (2.0 * np.pi * sigma1) * total)


def test_fem_matches_two_layer_closed_form():
    arr = _centre_electrode()
    sigma1, sigma2, h = 1.0, 0.3, 50.0  # a resistive layer buried below sigma1
    cond = LayeredConductivity(layers=(Layer(sigma1, h), Layer(sigma2, 2950.0)))
    dom = M.FieldDomain(
        arr, cond, half_width_um=3000.0, depth_um=3000.0, h_electrode_um=3.0, h_far_um=400.0
    )

    zs = np.array([20.0, 30.0, 40.0])  # all inside layer 1 (z < h)
    q = np.column_stack([np.zeros_like(zs), np.zeros_like(zs), zs])

    a_fem = solve_transfer_matrix(dom, q, degree=1)[:, 0]
    a_cf = np.array([_two_layer_surface_source(0.0, z, sigma1, sigma2, h) for z in zs])
    rel = np.abs(a_fem - a_cf) / np.abs(a_cf)
    assert np.median(rel) < 0.06, f"median rel err {np.median(rel):.3f}"
    assert np.max(rel) < 0.08, f"max rel err {np.max(rel):.3f}"

    # the value-add: the buried resistive layer banks the current up, raising the
    # layer-1 potential well above the homogeneous-sigma1 field the analytical
    # backend would give -- a large effect (not a rounding correction).
    a_homog = AnalyticalBackend().transfer_matrix(arr, HomogeneousConductivity(sigma1), q)[:, 0]
    assert np.all(a_fem > 1.2 * a_homog)


def test_layered_mms_recovers_flux_continuous_solution(tmp_path):
    """A piecewise-linear V that is continuous with continuous flux (sigma1 A1 =
    sigma2 A2) is a source-free exact solution; with the interface meshed, a P1
    space represents it exactly, so the layered assembly must recover it to
    machine precision. Uses the backend's own _build_sigma (the production path)."""
    arr = _centre_electrode()
    sigma1, sigma2, h, depth = 1.0, 0.3, 40.0, 100.0
    cond = LayeredConductivity(layers=(Layer(sigma1, h), Layer(sigma2, depth - h)))
    dom = M.FieldDomain(arr, cond, 100.0, depth, 6.0, 30.0)
    res = M.build_mesh(dom, str(tmp_path / "mms_layered.msh"))
    data = read_from_msh(res.path, MPI.COMM_WORLD, gdim=3)
    msh = data.mesh  # microns

    V = fem.functionspace(msh, ("Lagrange", 1))
    slope2 = sigma1 / sigma2  # A2 = (sigma1/sigma2) A1, with A1 = 1

    def exact(x: np.ndarray) -> np.ndarray:
        z = x[2]
        return np.where(z <= h, z, h + slope2 * (z - h))

    u_exact = fem.Function(V)
    u_exact.interpolate(exact)
    msh.topology.create_connectivity(2, 3)
    boundary = dmesh.exterior_facet_indices(msh.topology)
    bc = fem.dirichletbc(u_exact, fem.locate_dofs_topological(V, 2, boundary))

    u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
    sigma = _build_sigma(msh, data.cell_tags, dom, fem, default_scalar_type)
    a = sigma * ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx
    L = fem.Constant(msh, default_scalar_type(0.0)) * v * ufl.dx
    uh = LinearProblem(
        a,
        L,
        bcs=[bc],
        petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
        petsc_options_prefix="retinode_mms_layered_",
    ).solve()

    err = np.sqrt(
        msh.comm.allreduce(fem.assemble_scalar(fem.form((uh - u_exact) ** 2 * ufl.dx)), op=MPI.SUM)
    )
    scale = np.sqrt(
        msh.comm.allreduce(fem.assemble_scalar(fem.form(u_exact**2 * ufl.dx)), op=MPI.SUM)
    )
    assert err / scale < 1e-10, f"layered MMS rel L2 error {err / scale:.2e}"


def test_conductive_layer_lowers_the_field_relative_to_homogeneous():
    """Sign check on the layer effect: a *more* conductive buried layer (sigma2 >
    sigma1) drains current downward, lowering the layer-1 potential below the
    homogeneous-sigma1 field -- the opposite sign to the resistive case above."""
    arr = _centre_electrode()
    sigma1, sigma2, h = 1.0, 3.0, 50.0
    cond = LayeredConductivity(layers=(Layer(sigma1, h), Layer(sigma2, 2950.0)))
    dom = M.FieldDomain(arr, cond, 3000.0, 3000.0, 3.0, 400.0)
    q = np.array([[0.0, 0.0, 30.0]])
    a_fem = solve_transfer_matrix(dom, q, degree=1)[0, 0]
    a_homog = AnalyticalBackend().transfer_matrix(arr, HomogeneousConductivity(sigma1), q)[0, 0]
    assert a_fem < a_homog
