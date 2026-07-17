"""Neutral parametric geometry -> gmsh mesh for the FEM field backends.

The FEM backends (DOLFINx now, NGSolve as the cross-check) both read *one* mesh
built here, so the geometry is defined once and the two solvers cannot disagree
about it (Phase-4 D6). The geometry is a finite truncation of the epiretinal
half-space:

    - the array/substrate plane is z = 0 (matching the analytical backend, whose
      insulating image plane is also z = 0);
    - tissue fills the slab 0 <= z <= depth, laterally |x|,|y| <= half_width;
    - electrode faces (disk / square / hex / polygon) are imprinted on the top face
      z = 0 and tagged one surface each -- that is where the current is injected (a
      Neumann flux in the weak form, applied per electrode by the backend);
    - the rest of the top face is the insulating substrate (natural zero-flux);
    - the outer boundary (sides + bottom) is a grounded far-field truncation
      (Dirichlet V = 0);
    - the slab is split into one volume per conductivity layer, tagged so the
      backend can assign a sigma (or diagonal anisotropy) per layer.

This module is split so the *pure geometry* -- domain sizing, the layer
partition, tag conventions, validation -- imports and tests without gmsh (the
fast suite), while :func:`build_mesh` (which needs gmsh) is exercised only in the
``fem`` job. Import gmsh lazily for exactly that reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.spec import (
    ConductivityModel,
    ElectrodeArray,
    HomogeneousConductivity,
    LayeredConductivity,
)
from engine.spec.geometry import (
    apply_placement,
    electrode_area_um2,
    electrode_outline,
    radius_um,
)

Vec3 = tuple[float, float, float]

# 2D electrode faces the mesh can imprint on the array plane.
SUPPORTED_SHAPES = ("disk", "square", "hex", "poly")

# Physical-group tag conventions. Surfaces (dim 2) and volumes (dim 3) live in
# separate gmsh namespaces, so the small integers do not collide across dims.
GROUND_TAG = 1  # grounded far-field boundary (sides + bottom): Dirichlet V = 0
INSULATING_TAG = 2  # the substrate: rest of the top face, natural zero-flux
ELECTRODE_TAG_BASE = 10  # electrode i -> ELECTRODE_TAG_BASE + i (surface)
LAYER_TAG_BASE = 1  # layer i -> LAYER_TAG_BASE + i (volume)


@dataclass(frozen=True)
class LayerSlab:
    """One conductivity slab of the meshed domain, z0 <= z <= z1 (microns)."""

    index: int
    z0_um: float
    z1_um: float
    sigma_S_per_m: float
    anisotropy: Vec3 | None  # diagonal (sx, sy, sz); None = isotropic


@dataclass(frozen=True)
class FieldDomain:
    """The finite geometry a FEM backend meshes and solves on.

    ``half_width_um`` / ``depth_um`` truncate the half-space; the truncation is
    grounded, so both should comfortably exceed the electrode span (the far
    field decays like 1/r, so a few electrode-pitches of margin is plenty).
    ``h_electrode_um`` / ``h_far_um`` are the target mesh sizes at the electrode
    surfaces (fine, where the field is sharp) and at the outer boundary (coarse).
    """

    array: ElectrodeArray
    conductivity: ConductivityModel
    half_width_um: float
    depth_um: float
    h_electrode_um: float
    h_far_um: float

    def descriptor(self) -> str:
        """Canonical string of the numeric mesh/extent parameters — the part of
        a FEM solve's identity *beyond* the array and conductivity. Threaded into
        ``field_key`` (as ``solve_params``) so a coarse mesh's transfer matrix is
        never silently reused for a finer one. ``%.6g`` is finer than any mesh
        size we choose, so equal domains give equal descriptors."""
        return (
            f"hw={self.half_width_um:.6g};d={self.depth_um:.6g};"
            f"he={self.h_electrode_um:.6g};hf={self.h_far_um:.6g}"
        )

    def refined(self, factor: float) -> FieldDomain:
        """Same geometry, mesh sizes divided by ``factor`` -- the knob P4 S4's
        convergence study turns. ``factor > 1`` refines."""
        if factor <= 0:
            raise ValueError("refine factor must be positive")
        return FieldDomain(
            array=self.array,
            conductivity=self.conductivity,
            half_width_um=self.half_width_um,
            depth_um=self.depth_um,
            h_electrode_um=self.h_electrode_um / factor,
            h_far_um=self.h_far_um / factor,
        )


@dataclass(frozen=True)
class MeshResult:
    """A written gmsh mesh plus the tag maps a FEM backend needs to apply BCs.

    ``electrode_tags`` is keyed by electrode id (order preserved), so the backend
    injects unit current on one electrode at a time by its physical tag.
    ``layer_tags`` is aligned with :func:`layer_partition`.
    """

    path: str
    electrode_tags: dict[str, int]
    layer_tags: tuple[int, ...]
    ground_tag: int
    insulating_tag: int


def layer_partition(domain: FieldDomain) -> tuple[LayerSlab, ...]:
    """Split the domain into conductivity slabs, ordered from the surface (z=0)
    downward. Homogeneous -> a single slab spanning the whole depth. Layered ->
    one slab per layer; the layer thicknesses must sum to the domain depth."""
    cond = domain.conductivity
    if isinstance(cond, HomogeneousConductivity):
        return (LayerSlab(0, 0.0, domain.depth_um, cond.sigma_S_per_m, None),)
    if isinstance(cond, LayeredConductivity):
        slabs: list[LayerSlab] = []
        z = 0.0
        for i, layer in enumerate(cond.layers):
            z1 = z + layer.thickness_um
            slabs.append(LayerSlab(i, z, z1, layer.sigma_S_per_m, layer.anisotropy))
            z = z1
        if abs(z - domain.depth_um) > 1e-6 * max(1.0, domain.depth_um):
            raise ValueError(
                f"layer thicknesses sum to {z} um but domain depth is "
                f"{domain.depth_um} um; they must match for a layered domain"
            )
        return tuple(slabs)
    raise TypeError(f"unsupported conductivity model: {type(cond).__name__}")


def validate_domain(domain: FieldDomain) -> None:
    """Cheap geometry sanity checks -- caught here, in the fast suite, rather
    than as a cryptic gmsh failure. Electrodes must sit on z=0, be a supported 2D
    shape (disk/square/hex/poly), and fit inside the top face with a margin; the
    mesh sizes must be sane."""
    if domain.half_width_um <= 0 or domain.depth_um <= 0:
        raise ValueError("domain half_width and depth must be positive")
    if not (0 < domain.h_electrode_um <= domain.h_far_um):
        raise ValueError("need 0 < h_electrode_um <= h_far_um")
    if not domain.array.electrodes:
        raise ValueError("domain has no electrodes")
    for e in apply_placement(domain.array):  # validate the placed (posed) geometry
        if e.shape not in SUPPORTED_SHAPES:
            raise ValueError(
                f"electrode {e.id!r} has shape {e.shape!r}; mesh supports {SUPPORTED_SHAPES}"
            )
        if e.shape == "poly" and not e.boundary_um:
            raise ValueError(f"polygon electrode {e.id!r} has no boundary_um outline")
        x, y, z = e.pos_um
        if abs(z) > 1e-9:
            raise ValueError(f"electrode {e.id!r} is at z={z}; must sit on the plane z=0")
        r = radius_um(e)
        if max(abs(x), abs(y)) + r >= domain.half_width_um:
            raise ValueError(
                f"electrode {e.id!r} (center {x, y}, r={r}) reaches the outer "
                f"boundary at half_width={domain.half_width_um}; enlarge the domain"
            )
    # a layered domain must have thicknesses matching the depth
    layer_partition(domain)


def default_domain(
    array: ElectrodeArray,
    conductivity: ConductivityModel,
    *,
    margin_factor: float = 6.0,
    depth_um: float | None = None,
    cells_per_radius: float = 2.5,
) -> FieldDomain:
    """A reasonable domain auto-sized around an array: lateral margin scaled to
    the electrode span, depth from the layer stack (or ``margin_factor`` * span
    if homogeneous), and mesh sizes from the smallest electrode radius. Handy for
    tests and P4 S2; production runs can size the domain explicitly."""
    placed = apply_placement(array)  # size the domain around the posed positions
    xs = [e.pos_um[0] for e in placed]
    ys = [e.pos_um[1] for e in placed]
    radii = [radius_um(e) for e in placed]
    if not radii:
        raise ValueError("array has no electrodes")
    span = max(
        max(xs) - min(xs),
        max(ys) - min(ys),
        2.0 * max(radii),
    )
    reach = max(abs(v) for v in (*xs, *ys)) + max(radii)
    half_width = reach + margin_factor * max(span, max(radii))

    if isinstance(conductivity, LayeredConductivity):
        depth = sum(layer.thickness_um for layer in conductivity.layers)
    else:
        depth = depth_um if depth_um is not None else margin_factor * span

    h_electrode = min(radii) / cells_per_radius
    h_far = half_width / 4.0
    domain = FieldDomain(
        array=array,
        conductivity=conductivity,
        half_width_um=half_width,
        depth_um=depth,
        h_electrode_um=h_electrode,
        h_far_um=max(h_far, h_electrode),
    )
    validate_domain(domain)
    return domain


def _add_electrode_face(occ, electrode):
    """Create the electrode's 2D face on z=0 in the OCC kernel (to be imprinted).
    A disk is a native OCC disk; square/hex/poly are plane surfaces from the shared
    :func:`engine.spec.geometry.electrode_outline` vertices."""
    outline = electrode_outline(electrode)
    if outline is None:  # disk
        r = radius_um(electrode)
        return occ.addDisk(electrode.pos_um[0], electrode.pos_um[1], 0.0, r, r)
    pts = [occ.addPoint(vx, vy, 0.0) for (vx, vy) in outline]
    n = len(pts)
    lines = [occ.addLine(pts[k], pts[(k + 1) % n]) for k in range(n)]
    return occ.addPlaneSurface([occ.addCurveLoop(lines)])


def _expected_footprint(electrode) -> tuple[float, float, float]:
    """(centroid_x, centroid_y, area) of the electrode face, used to re-identify
    each electrode's surface after gmsh fragments the top plane. Disk/square/hex
    are centred on ``pos_um``; a polygon uses its area-weighted centroid."""
    area = electrode_area_um2(electrode)
    outline = electrode_outline(electrode)
    if outline is None or electrode.shape != "poly":  # disk/square/hex centred on pos
        return electrode.pos_um[0], electrode.pos_um[1], area
    a2 = cx = cy = 0.0
    n = len(outline)
    for k in range(n):
        x0, y0 = outline[k]
        x1, y1 = outline[(k + 1) % n]
        cross = x0 * y1 - x1 * y0
        a2 += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if abs(a2) < 1e-12:  # degenerate outline -> fall back to the vertex mean
        return sum(v[0] for v in outline) / n, sum(v[1] for v in outline) / n, area
    return cx / (3.0 * a2), cy / (3.0 * a2), area


def _build_electrode_surfaces(gmsh, occ, domain, boxes, electrodes, eps):  # noqa: ANN001 - gmsh
    """Build every electrode on the tissue and identify its conductive surface(s).
    Flat electrodes imprint a face on the top plane; body electrodes are cut from
    the tissue and their cavity walls split conductive/insulated. One build handles
    any **mix** of the two. Returns (electrode_surf {id: [surf]}, insulating, ground).
    """
    from engine.spec.geometry import placement_rotation

    from .mesh3d import add_body_solid, classify_cavity_surfaces

    w, depth = domain.half_width_um, domain.depth_um
    rotation = placement_rotation(domain.array)  # the array tilt (identity if none)
    flats = [e for e in electrodes if e.body is None]
    bodies = [e for e in electrodes if e.body is not None]

    # Cut the 3D bodies from the tissue, then imprint the flat faces on the result.
    # OCC boolean ops work on OCC tags directly; synchronize pushes to the model.
    if bodies:
        body_tags = {e.id: add_body_solid(occ, e, rotation) for e in bodies}
        occ.cut([(3, b) for b in boxes], [(3, body_tags[e.id]) for e in bodies], removeTool=True)
        occ.synchronize()
        vol_dimtags = gmsh.model.getEntities(3)  # the reshaped tissue volumes
    else:
        vol_dimtags = [(3, b) for b in boxes]  # not yet synchronized; use the box tags
    if flats:
        faces = [_add_electrode_face(occ, e) for e in flats]
        occ.fragment(vol_dimtags, [(2, f) for f in faces])
    occ.synchronize()

    volumes = [tag for (dim, tag) in gmsh.model.getEntities(3)]
    boundary = gmsh.model.getBoundary([(3, v) for v in volumes], combined=True, oriented=False)
    top_faces: list[int] = []
    ground_faces: list[int] = []
    wall_faces: list[int] = []
    for _dim, surf in boundary:
        cx, cy, cz = occ.getCenterOfMass(2, surf)
        far = (
            abs(abs(cx) - w) <= 1e-3 * w
            or abs(abs(cy) - w) <= 1e-3 * w
            or abs(cz - depth) <= 1e-3 * depth
        )
        if far:
            ground_faces.append(surf)
        elif abs(cz) <= eps:
            top_faces.append(surf)  # z=0 plane: a flat electrode or the substrate
        else:
            wall_faces.append(surf)  # a cavity wall (a 3D electrode-tissue interface)

    electrode_surf: dict[str, list[int]] = {}
    insulating_faces: list[int] = []

    # Flat electrodes: match a top face by expected centroid + area; the rest of
    # the top plane is the insulating substrate.
    footprints = {e.id: _expected_footprint(e) for e in flats}
    matched: set[int] = set()
    for surf in top_faces:
        cx, cy, _cz = occ.getCenterOfMass(2, surf)
        area = occ.getMass(2, surf)
        for e in flats:
            if e.id in electrode_surf:
                continue
            ex, ey, e_area = footprints[e.id]
            char = math.sqrt(e_area)  # characteristic length for the tolerance
            if math.dist((cx, cy), (ex, ey)) <= 0.25 * char and abs(area - e_area) <= 0.1 * e_area:
                electrode_surf[e.id] = [surf]
                matched.add(surf)
                break
    insulating_faces.extend(s for s in top_faces if s not in matched)
    missing = [e.id for e in flats if e.id not in electrode_surf]
    if missing:
        raise RuntimeError(f"gmsh did not imprint electrode surface(s): {missing}")

    # Body electrodes: assign each cavity wall to the nearest body, split its faces.
    if bodies:
        walls: dict[str, list[int]] = {e.id: [] for e in bodies}
        for surf in wall_faces:
            cx, cy, _cz = occ.getCenterOfMass(2, surf)
            nearest = min((math.dist((cx, cy), (e.pos_um[0], e.pos_um[1])), e.id) for e in bodies)
            walls[nearest[1]].append(surf)
        for e in bodies:
            conductive, insulated = classify_cavity_surfaces(occ, e, walls[e.id], rotation)
            if not conductive:
                raise RuntimeError(f"electrode {e.id!r} has no conductive surface after the cut")
            electrode_surf[e.id] = conductive
            insulating_faces.extend(insulated)
    else:
        insulating_faces.extend(wall_faces)  # none expected when all electrodes are flat

    return electrode_surf, insulating_faces, ground_faces


def build_mesh(domain: FieldDomain, path: str) -> MeshResult:
    """Mesh ``domain`` with gmsh and write it to ``path`` (a ``.msh`` file both
    DOLFINx and NGSolve read). Returns the physical-group tags a backend applies
    BCs against. Requires gmsh (the ``fem`` env); imported lazily so the pure
    geometry above stays importable without it.
    """
    import gmsh  # lazy: only the fem env has it

    validate_domain(domain)
    slabs = layer_partition(domain)
    w = domain.half_width_um
    electrodes = apply_placement(domain.array)  # positions posed into the tissue (P6 S3)
    radii = [radius_um(e) for e in electrodes]

    gmsh.initialize()
    try:
        gmsh.model.add("retinode")
        occ = gmsh.model.occ

        # One box per layer, stacked in z, then joined into a conformal solid so
        # the layer interfaces are shared (matched) surfaces.
        boxes = [occ.addBox(-w, -w, s.z0_um, 2 * w, 2 * w, s.z1_um - s.z0_um) for s in slabs]
        eps = 1e-6 * domain.depth_um

        electrode_surf, insulating_faces, ground_faces = _build_electrode_surfaces(
            gmsh, occ, domain, boxes, electrodes, eps
        )
        volumes = [tag for (dim, tag) in gmsh.model.getEntities(3)]

        # Assign each volume to the layer whose z-range holds its centroid.
        layer_vols: dict[int, list[int]] = {s.index: [] for s in slabs}
        for v in volumes:
            _cx, _cy, cz = occ.getCenterOfMass(3, v)
            for s in slabs:
                if s.z0_um - eps <= cz <= s.z1_um + eps:
                    layer_vols[s.index].append(v)
                    break

        # Physical groups (the tags a backend applies BCs against).
        gmsh.model.addPhysicalGroup(2, ground_faces, GROUND_TAG)
        gmsh.model.setPhysicalName(2, GROUND_TAG, "ground")
        gmsh.model.addPhysicalGroup(2, insulating_faces, INSULATING_TAG)
        gmsh.model.setPhysicalName(2, INSULATING_TAG, "insulating")
        electrode_tags: dict[str, int] = {}
        for i, e in enumerate(electrodes):
            tag = ELECTRODE_TAG_BASE + i
            gmsh.model.addPhysicalGroup(2, electrode_surf[e.id], tag)
            gmsh.model.setPhysicalName(2, tag, f"electrode_{e.id}")
            electrode_tags[e.id] = tag
        layer_tags: list[int] = []
        for s in slabs:
            tag = LAYER_TAG_BASE + s.index
            gmsh.model.addPhysicalGroup(3, layer_vols[s.index], tag)
            gmsh.model.setPhysicalName(3, tag, f"layer_{s.index}")
            layer_tags.append(tag)

        # Graded sizing: fine at the electrode (conductive) surfaces, coarse to the shell.
        dist = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(
            dist, "FacesList", [s for e in electrodes for s in electrode_surf[e.id]]
        )
        thr = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(thr, "InField", dist)
        gmsh.model.mesh.field.setNumber(thr, "SizeMin", domain.h_electrode_um)
        gmsh.model.mesh.field.setNumber(thr, "SizeMax", domain.h_far_um)
        gmsh.model.mesh.field.setNumber(thr, "DistMin", max(radii))
        gmsh.model.mesh.field.setNumber(thr, "DistMax", domain.half_width_um)
        gmsh.model.mesh.field.setAsBackgroundMesh(thr)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)

        gmsh.model.mesh.generate(3)
        # Write MSH 2.2: DOLFINx reads it (via the gmsh API) *and* so does
        # netgen's ReadGmsh, which only parses 2.2 -- so both FEM backends read
        # the one file (the P4 S5 cross-check reads the same mesh, not two builds).
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.write(path)
    finally:
        gmsh.finalize()

    return MeshResult(
        path=path,
        electrode_tags=electrode_tags,
        layer_tags=tuple(layer_tags),
        ground_tag=GROUND_TAG,
        insulating_tag=INSULATING_TAG,
    )
