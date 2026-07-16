"""NGSolve field backend: an independent second solver for the FEM cross-check.

Solves the *same* quasi-static problem as :mod:`engine.field.fem_fenicsx`, on the
*same* gmsh mesh (netgen's ``ReadGmsh`` and DOLFINx both read the MSH 2.2 file
:func:`engine.field.mesh.build_mesh` writes), with the same boundary conditions
and the same mV/uA unit chain. Two independent FEM libraries agreeing on one mesh
is the "confirmed by a second backend" evidence Phase 4 is done when it has
(Phase-4 D2): a bug in either solver's assembly or BC handling would break the
agreement.

Units: rather than rescale the netgen mesh, this solves directly in microns with
an effective conductivity ``sigma * 1e-6`` (the microns->metres fold of the weak
form), so V comes out in volts for a 1 A injection, and ``A = 1e-3 * V`` gives
mV/uA -- identical to the DOLFINx backend.

Requires ngsolve (a pip universal2 wheel that coexists with the conda DOLFINx in
the FEM env); imported lazily so the module loads under uv without it.
"""

from __future__ import annotations

import numpy as np

from engine.spec import (
    ConductivityModel,
    ElectrodeArray,
    HomogeneousConductivity,
)

from .fem_fenicsx import _reject_anisotropy
from .mesh import FieldDomain, MeshResult, build_mesh, default_domain, layer_partition

_MV_PER_UA_FROM_SI = 1.0e-3
_UM_TO_M_FOLD = 1.0e-6  # sigma * this folds the microns->metres unit change into the form


class NGSolveBackend:
    """FEM field backend (NGSolve) behind the transfer-matrix contract -- the
    independent cross-check of :class:`~engine.field.fem_fenicsx.FenicsxBackend`.
    Same domain auto-sizing, same homogeneous/isotropic-layered support, same
    anisotropy deferral."""

    def __init__(
        self,
        *,
        domain: FieldDomain | None = None,
        degree: int = 1,
        margin_factor: float = 6.0,
    ) -> None:
        self.name = "fem_ngsolve"
        self._domain = domain
        self.degree = degree
        self.margin_factor = margin_factor

    def transfer_matrix(
        self,
        array: ElectrodeArray,
        conductivity: ConductivityModel,
        query_points_um: np.ndarray,
    ) -> np.ndarray:
        _reject_anisotropy(conductivity)
        domain = self._domain or default_domain(
            array, conductivity, margin_factor=self.margin_factor
        )
        if domain.array is not array and domain.array.ids() != array.ids():
            raise ValueError("the backend's domain was built for a different array")
        return solve_transfer_matrix_ngsolve(domain, query_points_um, degree=self.degree)


def solve_transfer_matrix_ngsolve(
    domain: FieldDomain,
    query_points_um: np.ndarray,
    *,
    degree: int = 1,
    _mesh_path: str | None = None,
) -> np.ndarray:
    """NGSolve counterpart of
    :func:`engine.field.fem_fenicsx.solve_transfer_matrix`: build the mesh, solve
    one unit-current problem per electrode, sample -> A (mV/uA)."""
    import tempfile

    _reject_anisotropy(domain.conductivity)
    if _mesh_path is not None:
        result = build_mesh(domain, _mesh_path)
        return _solve_on_mesh_ngsolve(result, domain, query_points_um, degree)
    with tempfile.TemporaryDirectory() as tmp:
        result = build_mesh(domain, f"{tmp}/domain.msh")
        return _solve_on_mesh_ngsolve(result, domain, query_points_um, degree)


def _solve_on_mesh_ngsolve(
    result: MeshResult,
    domain: FieldDomain,
    query_points_um: np.ndarray,
    degree: int,
) -> np.ndarray:
    """The NGSolve core: read the tagged 2.2 mesh (by physical-group *name*),
    assemble once (the stiffness matrix is shared across electrodes), and solve a
    unit-current Neumann problem per electrode. Returns A (mV/uA)."""
    import ngsolve as ng
    from netgen.read_gmsh import ReadGmsh

    mesh = ng.Mesh(ReadGmsh(result.path))
    sigma = _sigma_cf(mesh, domain, ng)

    fes = ng.H1(mesh, order=degree, dirichlet="ground")  # V = 0 on the grounded shell
    u, v = fes.TnT()
    a = ng.BilinearForm(sigma * ng.grad(u) * ng.grad(v) * ng.dx)
    a.Assemble()
    inv = a.mat.Inverse(fes.FreeDofs(), inverse="sparsecholesky")  # factor once, reuse

    q = np.asarray(query_points_um, dtype=float).reshape(-1, 3)
    columns: list[np.ndarray] = []
    for eid in result.electrode_tags:  # electrode order preserved
        bnd = mesh.Boundaries(f"electrode_{eid}")
        area = ng.Integrate(ng.CoefficientFunction(1.0) * ng.ds(definedon=bnd), mesh)
        f = ng.LinearForm((1.0 / area) * v * ng.ds(definedon=bnd))
        f.Assemble()
        gfu = ng.GridFunction(fes)
        gfu.vec.data = inv * f.vec
        ve_volts = np.array([gfu(mesh(x, y, z)) for x, y, z in q], dtype=float)
        columns.append(ve_volts * _MV_PER_UA_FROM_SI)
    return np.column_stack(columns)


def _sigma_cf(mesh, domain, ng):  # noqa: ANN001
    """Effective conductivity (sigma * 1e-6) as an NGSolve CoefficientFunction:
    a scalar for homogeneous, or per-material (indexed by the ``layer_i`` region
    the mesh tags) for layered."""
    cond = domain.conductivity
    if isinstance(cond, HomogeneousConductivity):
        return ng.CoefficientFunction(cond.sigma_S_per_m * _UM_TO_M_FOLD)
    sigma_by_name = {
        f"layer_{s.index}": s.sigma_S_per_m * _UM_TO_M_FOLD for s in layer_partition(domain)
    }
    # CoefficientFunction(list) maps material region i -> list[i]
    return ng.CoefficientFunction([sigma_by_name[m] for m in mesh.GetMaterials()])
