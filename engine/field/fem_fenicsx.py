"""DOLFINx field backend: the transfer matrix by finite elements.

Solves the quasi-static conduction problem ``-div(sigma grad V) = 0`` on the
truncated tissue slab meshed in :mod:`engine.field.mesh`, one unit-current solve
per electrode. Because the top face z=0 is meshed as an insulating boundary
except at the electrodes, the half-space image the analytical backend adds by
hand is enforced *geometrically* here -- the FEM slab already is the half-space.

The boundary conditions realise the electrode contract:

    - each electrode surface carries a Neumann flux ``sigma dV/dn = I / area`` --
      a unit current spread uniformly over the disk (weak-form RHS
      ``(I/area) * integral(v) dS``);
    - the rest of the top face is insulating: the natural zero-flux BC, nothing
      to impose;
    - the outer shell (sides + bottom) is grounded, ``V = 0`` (Dirichlet), the
      far-field truncation.

Linearity means one solve per electrode with unit current gives one column of A;
any stimulus is then ``Ve = A @ I`` (see backend.py). Units: the mesh is scaled
from microns to metres so the assembly is pure SI (V for I in amps), then A is
returned in mV/uA via ``A_mV/uA = 1e-3 * V_volts`` (see spec/conventions.py and
the analytical backend, which this must match on a homogeneous half-space).

Requires the FEM conda env (dolfinx); imported lazily so the module -- and the
cheap guards on it -- import under uv without dolfinx.
"""

from __future__ import annotations

import numpy as np

from engine.spec import (
    ConductivityModel,
    ElectrodeArray,
    HomogeneousConductivity,
    LayeredConductivity,
)

from .mesh import (
    LAYER_TAG_BASE,
    FieldDomain,
    MeshResult,
    build_mesh,
    default_domain,
    layer_partition,
)

# V[volts] per I[amps] -> A[mV/uA]; mV/uA = 1e-3 * V/A. Matches analytical.py.
_MV_PER_UA_FROM_SI = 1.0e-3
_UM_TO_M = 1.0e-6


class FenicsxBackend:
    """FEM field backend (DOLFINx) behind the transfer-matrix contract.

    The domain (extent + mesh resolution) is auto-sized from the array via
    :func:`engine.field.mesh.default_domain` unless one is passed explicitly.
    ``degree`` is the Lagrange element order (1 is enough for the potential; 2
    sharpens the near field at more cost). Homogeneous and (isotropic) layered
    conductivity are both supported; diagonal anisotropy is a planned extension
    and raises NotImplementedError for now.
    """

    def __init__(
        self,
        *,
        domain: FieldDomain | None = None,
        degree: int = 1,
        margin_factor: float = 6.0,
    ) -> None:
        self.name = "fem_fenicsx"
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
        domain = self._resolve_domain(array, conductivity)
        if domain.array is not array and domain.array.ids() != array.ids():
            raise ValueError("the backend's domain was built for a different array")
        return solve_transfer_matrix(domain, query_points_um, degree=self.degree)

    def _resolve_domain(
        self, array: ElectrodeArray, conductivity: ConductivityModel
    ) -> FieldDomain:
        return self._domain or default_domain(
            array, conductivity, margin_factor=self.margin_factor
        )

    def solve_params(self, array: ElectrodeArray, conductivity: ConductivityModel) -> str:
        """Canonical string of the solve settings that change ``A`` beyond the
        array and conductivity: the element degree and the mesh resolution/extent
        (the resolved domain's :meth:`~engine.field.mesh.FieldDomain.descriptor`).
        Pass to ``field_key(..., solve_params=...)`` so a FEM transfer matrix is
        cache-keyed to its mesh and never reused across refinements."""
        _reject_anisotropy(conductivity)
        return f"deg={self.degree}|{self._resolve_domain(array, conductivity).descriptor()}"


def solve_transfer_matrix(
    domain: FieldDomain,
    query_points_um: np.ndarray,
    *,
    degree: int = 1,
    _mesh_path: str | None = None,
) -> np.ndarray:
    """Build the mesh for ``domain``, solve one unit-current problem per
    electrode, and sample the potential at ``query_points_um`` -> A (mV/uA),
    shape (n_query, n_electrodes), columns ordered as ``domain.array``.
    """
    import tempfile

    _reject_anisotropy(domain.conductivity)

    if _mesh_path is not None:
        result = build_mesh(domain, _mesh_path)
        cols = _solve_on_mesh(result, domain, query_points_um, degree)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            result = build_mesh(domain, f"{tmp}/domain.msh")
            cols = _solve_on_mesh(result, domain, query_points_um, degree)
    return cols


def _reject_anisotropy(conductivity: ConductivityModel) -> None:
    """Diagonal anisotropy is a planned extension; refuse it early (before any
    mesh build or dolfinx import) so the guard is cheap and fast-testable."""
    if isinstance(conductivity, LayeredConductivity) and any(
        layer.anisotropy is not None for layer in conductivity.layers
    ):
        raise NotImplementedError(
            "anisotropic layers are not yet supported by the FEM backend; use "
            "isotropic per-layer conductivities (diagonal anisotropy is planned)"
        )


def _solve_on_mesh(
    result: MeshResult,
    domain: FieldDomain,
    query_points_um: np.ndarray,
    degree: int,
) -> np.ndarray:
    """The DOLFINx core: read the tagged mesh, assemble ``sigma grad u . grad v``
    with V=0 on the ground shell, and solve a unit-current Neumann problem per
    electrode. ``sigma`` is a constant (homogeneous) or a per-layer DG0 field
    (layered). Returns A (mV/uA) sampled at the query points."""
    import ufl
    from dolfinx import default_scalar_type, fem
    from dolfinx.fem.petsc import LinearProblem
    from dolfinx.io.gmsh import read_from_msh
    from mpi4py import MPI

    data = read_from_msh(result.path, MPI.COMM_WORLD, gdim=3)
    mesh = data.mesh
    facet_tags = data.facet_tags
    cell_tags = data.cell_tags

    # microns -> metres so the assembly is pure SI.
    mesh.geometry.x[:] *= _UM_TO_M

    V = fem.functionspace(mesh, ("Lagrange", degree))
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    sigma = _build_sigma(mesh, cell_tags, domain, fem, default_scalar_type)
    a = sigma * ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx

    # V = 0 on the grounded far-field shell.
    ground_facets = facet_tags.find(result.ground_tag)
    mesh.topology.create_connectivity(mesh.topology.dim - 1, mesh.topology.dim)
    ground_dofs = fem.locate_dofs_topological(V, mesh.topology.dim - 1, ground_facets)
    u_ground = fem.Function(V)
    u_ground.x.array[:] = 0.0
    bc = fem.dirichletbc(u_ground, ground_dofs)

    ds = ufl.Measure("ds", domain=mesh, subdomain_data=facet_tags)
    query_m = np.asarray(query_points_um, dtype=float).reshape(-1, 3) * _UM_TO_M

    columns: list[np.ndarray] = []
    for eid in result.electrode_tags:  # dict preserves electrode order
        tag = result.electrode_tags[eid]
        area = _assemble_scalar(fem, mesh, MPI, fem.Constant(mesh, 1.0) * ds(tag))
        # unit current (1 A) spread uniformly over the disk -> flux 1/area.
        flux = fem.Constant(mesh, default_scalar_type(1.0 / area))
        L = flux * v * ds(tag)
        problem = LinearProblem(
            a,
            L,
            bcs=[bc],
            petsc_options={"ksp_type": "preonly", "pc_type": "lu"},
            petsc_options_prefix=f"retinode_fem_{tag}_",
        )
        vh = problem.solve()
        ve_volts = _eval_at_points(vh, mesh, query_m)  # volts, for I = 1 A
        columns.append(ve_volts * _MV_PER_UA_FROM_SI)

    return np.column_stack(columns)


def _build_sigma(mesh, cell_tags, domain, fem, default_scalar_type):
    """The conductivity coefficient for the bilinear form. Homogeneous -> a
    constant. Layered -> a DG0 (cell-wise constant) field taking each layer's
    sigma on the cells the mesh tagged for that layer, so the sigma jump sits
    exactly on the meshed interface (a conforming FEM then enforces V- and
    flux-continuity across it automatically)."""
    cond = domain.conductivity
    if isinstance(cond, HomogeneousConductivity):
        return fem.Constant(mesh, default_scalar_type(cond.sigma_S_per_m))

    slabs = layer_partition(domain)
    Q = fem.functionspace(mesh, ("DG", 0))  # one dof per cell
    sigma = fem.Function(Q)
    dof_of_cell = Q.dofmap.list.reshape(-1)  # DG0: cell -> its single dof
    for slab in slabs:
        cells = cell_tags.find(LAYER_TAG_BASE + slab.index)
        sigma.x.array[dof_of_cell[cells]] = slab.sigma_S_per_m
    return sigma


def _assemble_scalar(fem, mesh, MPI, form_expr) -> float:
    val = fem.assemble_scalar(fem.form(form_expr))
    return float(mesh.comm.allreduce(val, op=MPI.SUM))


def _eval_at_points(func, mesh, points_m: np.ndarray) -> np.ndarray:
    """Evaluate a scalar Function at arbitrary points (metres). Points must lie
    inside the meshed tissue -- a query point outside the domain is an error, not
    a silent zero."""
    from dolfinx import geometry

    tree = geometry.bb_tree(mesh, mesh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points_m)
    colliding = geometry.compute_colliding_cells(mesh, candidates, points_m)

    cells = np.empty(len(points_m), dtype=np.int32)
    for i in range(len(points_m)):
        links = colliding.links(i)
        if len(links) == 0:
            raise ValueError(
                f"query point {points_m[i] / _UM_TO_M} um is outside the FEM domain; "
                "enlarge the domain or move the point inside the tissue"
            )
        cells[i] = links[0]
    values = func.eval(points_m, cells)
    return np.asarray(values, dtype=float).reshape(-1)
