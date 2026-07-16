"""P4 S1 feasibility gate: DOLFINx solves a Poisson problem to a known answer.

This is the go/no-go for DOLFINx-first (Phase-4 D1). It is deliberately *decoupled*
from gmsh and from engine geometry -- a built-in unit-square mesh and a manufactured
solution -- so a failure here indicts the DOLFINx toolchain itself, not our mesh.

The manufactured solution u = 1 + x^2 + 2 y^2 is quadratic, so a P2 (quadratic
Lagrange) space represents it exactly; -Laplace(u) = -6 is the source. A correct
solver recovers u to solver tolerance (~1e-9), not merely to discretization error.
"""

from __future__ import annotations

import pytest

pytest.importorskip("dolfinx")

import numpy as np  # noqa: E402
import ufl  # noqa: E402
from dolfinx import default_scalar_type, fem, mesh  # noqa: E402
from dolfinx.fem.petsc import LinearProblem  # noqa: E402
from mpi4py import MPI  # noqa: E402

pytestmark = pytest.mark.fem


def _exact(x: np.ndarray) -> np.ndarray:
    return 1.0 + x[0] ** 2 + 2.0 * x[1] ** 2


def test_dolfinx_solves_poisson_to_known_answer() -> None:
    domain = mesh.create_unit_square(MPI.COMM_WORLD, 12, 12)
    V = fem.functionspace(domain, ("Lagrange", 2))

    u_exact = fem.Function(V)
    u_exact.interpolate(_exact)

    # Dirichlet u = u_exact on the whole boundary.
    domain.topology.create_connectivity(domain.topology.dim - 1, domain.topology.dim)
    boundary_facets = mesh.exterior_facet_indices(domain.topology)
    boundary_dofs = fem.locate_dofs_topological(V, domain.topology.dim - 1, boundary_facets)
    bc = fem.dirichletbc(u_exact, boundary_dofs)

    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    f = fem.Constant(domain, default_scalar_type(-6.0))
    a = ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx
    L = f * v * ufl.dx

    problem = LinearProblem(
        a,
        L,
        bcs=[bc],
        petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
        petsc_options_prefix="retinode_gate_",
    )
    uh = problem.solve()

    error = fem.form(ufl.inner(uh - u_exact, uh - u_exact) * ufl.dx)
    l2 = np.sqrt(domain.comm.allreduce(fem.assemble_scalar(error), op=MPI.SUM))
    assert l2 < 1e-9, f"DOLFINx Poisson L2 error {l2:.2e} exceeds gate tolerance"
