"""3D electrode bodies in the FEM mesh: build the solid, tag its surfaces (P6 S2).

The tissue domain is the slab *minus* the electrode body — a boolean cut done in
:func:`engine.field.mesh.build_mesh`. This module supplies the two body-specific
pieces: constructing the body solid in the OCC kernel, and, after the cut, splitting
its cavity-wall surfaces into **conductive** (Neumann flux) and **insulated**
(zero-flux) per the body's ``conductive_faces`` selector.

gmsh is imported lazily by the caller; these helpers only touch the ``occ`` object
they are handed, so the module imports without gmsh.
"""

from __future__ import annotations

import hashlib
import math

from engine.spec.body import CadBody, Cylinder, Frustum, Hemisphere

Mat3 = tuple[tuple[float, float, float], ...]
_IDENTITY3: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def _axis_angle(r: Mat3) -> tuple[tuple[float, float, float], float]:
    """A single (axis, angle-radians) for the rotation matrix ``r`` (for occ.rotate).
    Returns a null rotation for identity."""
    trace = r[0][0] + r[1][1] + r[2][2]
    angle = math.acos(max(-1.0, min(1.0, (trace - 1.0) / 2.0)))
    if angle < 1e-12:
        return (0.0, 0.0, 1.0), 0.0
    if abs(angle - math.pi) < 1e-9:  # 180 deg: axis from the largest diagonal term
        k = max(range(3), key=lambda i: r[i][i])
        axis = [0.0, 0.0, 0.0]
        axis[k] = math.sqrt(max(0.0, (r[k][k] + 1.0) / 2.0))
        n = math.sqrt(sum(a * a for a in axis)) or 1.0
        return (axis[0] / n, axis[1] / n, axis[2] / n), angle
    s = 2.0 * math.sin(angle)
    return (
        ((r[2][1] - r[1][2]) / s, (r[0][2] - r[2][0]) / s, (r[1][0] - r[0][1]) / s),
        angle,
    )


def _orient_and_place(occ, dimtags, electrode, rotation: Mat3) -> None:  # noqa: ANN001
    """Rotate a body (built axis-aligned at the origin) into the array's pose, then
    translate it to the electrode's placed base centre."""
    if rotation is not None and rotation != _IDENTITY3:
        (ax, ay, az), angle = _axis_angle(rotation)
        occ.rotate(dimtags, 0.0, 0.0, 0.0, ax, ay, az, angle)
    x, y, z = electrode.pos_um
    occ.translate(dimtags, x, y, z)


def add_body_solid(occ, electrode, rotation: Mat3 | None = None):  # noqa: ANN001
    """Create the electrode's 3D body as an OCC solid, built axis-aligned at the
    origin (protruding along +z), then oriented by ``rotation`` (the array's tilt)
    and translated to ``pos_um``. Cutting the (z >= 0) tissue box by this solid
    leaves the cavity whose walls inject current. ``rotation`` None/identity is the
    untilted case (a pure translation)."""
    body = electrode.body
    rotation = rotation or _IDENTITY3
    if isinstance(body, Hemisphere):
        # A full sphere is rotation-invariant; centred on the plane, its z<0 half is
        # outside the tissue box, so the cut removes exactly the z>=0 hemisphere.
        solid = occ.addSphere(0.0, 0.0, 0.0, body.radius_um)
    elif isinstance(body, Cylinder):
        solid = occ.addCylinder(0.0, 0.0, 0.0, 0.0, 0.0, body.height_um, body.radius_um)
    elif isinstance(body, Frustum):
        solid = occ.addCone(
            0.0, 0.0, 0.0, 0.0, 0.0, body.height_um, body.base_radius_um, body.top_radius_um
        )
    elif isinstance(body, CadBody):
        solid = occ.importShapes(body.cad_path)[0][1]  # its origin is the electrode base
    else:
        raise TypeError(f"unsupported electrode body: {type(body).__name__}")
    _orient_and_place(occ, [(3, solid)], electrode, rotation)
    return solid


def classify_cavity_surfaces(occ, electrode, wall_surfs, rotation: Mat3 | None = None):  # noqa: ANN001
    """Split an electrode's cavity-wall surfaces into ``(conductive, insulated)``
    per its body's ``conductive_faces``. A hemisphere and an imported CAD body are
    fully conductive (the whole exposed surface injects); for a cylinder/frustum the
    deep **tip** cap and the lateral **side** wall are separated by centroid depth in
    the **body-local frame** (so a tilted body classifies the same as an upright one),
    and the selector picks which conduct."""
    body = electrode.body
    if isinstance(body, Hemisphere):
        return list(wall_surfs), []  # a hemisphere is always fully conductive

    rotation = rotation or _IDENTITY3
    r_t = tuple(zip(*rotation, strict=True))  # transpose: world -> local
    ex, ey, ez = electrode.pos_um
    # the depth at which a face counts as "tip": near the deepest local extent
    height = body.bounding_height_um if isinstance(body, CadBody) else body.height_um
    tip: list[int] = []
    sides: list[int] = []
    for surf in wall_surfs:
        cx, cy, cz = occ.getCenterOfMass(2, surf)
        wx, wy, wz = cx - ex, cy - ey, cz - ez
        local_z = r_t[2][0] * wx + r_t[2][1] * wy + r_t[2][2] * wz
        (tip if local_z >= 0.75 * height else sides).append(surf)

    which = body.conductive_faces
    if which == "tip":
        return tip, sides
    if which == "sides":
        return sides, tip
    return tip + sides, []  # "all"


def load_cad_body(
    cad_path: str, *, conductive_faces: str = "all", overlap_mesh_size_um: float | None = None
) -> CadBody:
    """Read a STEP/BREP solid and build a :class:`~engine.spec.body.CadBody`: hash
    its content (the geometric identity, for provenance), measure its bounding
    radius/height and its exposed surface area (split tip/sides), and bake a coarse
    triangulated surface so the pure-Python overlap check can test point-in-solid
    exactly without gmsh (P6 S9). The CAD's origin is taken as the electrode's base
    on the array plane; the exposed area excludes the z=0 base face (the substrate
    opening, not a conductive surface). Requires gmsh (the fem env)."""
    import gmsh

    with open(cad_path, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()

    gmsh.initialize()
    try:
        gmsh.model.add("cad")
        occ = gmsh.model.occ
        solid = occ.importShapes(cad_path)[0]
        occ.synchronize()
        xmin, ymin, zmin, xmax, ymax, zmax = occ.getBoundingBox(*solid)
        bounding_radius = 0.5 * max(xmax - xmin, ymax - ymin)
        bounding_height = zmax - zmin
        # Sum the exposed area, and split it into a deep "tip" and lateral "sides"
        # by centroid depth (the same 0.75*height threshold the mesh uses to classify
        # cavity walls, so the load-time areas match the meshed conductive surfaces).
        # The z=0 base face is the substrate opening, not a conductive surface.
        tip_area = 0.0
        sides_area = 0.0
        for _dim, s in gmsh.model.getBoundary([solid], combined=True, oriented=False):
            cz = occ.getCenterOfMass(2, s)[2]
            if abs(cz) <= 1e-6:
                continue  # the z=0 base
            area = occ.getMass(2, s)
            if cz >= 0.75 * bounding_height:
                tip_area += area
            else:
                sides_area += area
        # A coarse surface triangulation of the whole closed solid (base included, so
        # the ray-parity point-in-solid test is watertight) for exact overlap.
        size = overlap_mesh_size_um or max(bounding_radius, bounding_height) / 6.0
        points, tris = _surface_triangulation(gmsh, size)
    finally:
        gmsh.finalize()

    return CadBody(
        cad_path=cad_path,
        content_hash=content_hash,
        bounding_radius_um=bounding_radius,
        bounding_height_um=bounding_height,
        surface_area_um2=tip_area + sides_area,
        conductive_faces=conductive_faces,  # type: ignore[arg-type]
        tip_area_um2=tip_area,
        sides_area_um2=sides_area,
        surface_points_um=points,
        surface_tris=tris,
    )


def _surface_triangulation(gmsh, size_um: float):  # noqa: ANN001
    """Surface-mesh the loaded solid at ``size_um`` and return ``(points, tris)`` —
    node coordinates (microns) and triangles indexing them — for the exact overlap
    proxy. The model already holds the synchronized solid."""
    gmsh.option.setNumber("Mesh.MeshSizeMax", size_um)
    gmsh.option.setNumber("Mesh.MeshSizeMin", size_um)
    gmsh.model.mesh.generate(2)  # surfaces only
    node_tags, coords, _ = gmsh.model.mesh.getNodes()
    coords = coords.reshape(-1, 3)
    tag_to_idx = {int(t): i for i, t in enumerate(node_tags)}
    points = tuple((float(x), float(y), float(z)) for x, y, z in coords)
    tris: list[tuple[int, int, int]] = []
    etypes, _etags, enodes = gmsh.model.mesh.getElements(dim=2)
    for et, conn in zip(etypes, enodes, strict=True):
        if et == 2:  # 3-node triangle
            flat = [int(n) for n in conn]
            tris.extend(
                (tag_to_idx[flat[i]], tag_to_idx[flat[i + 1]], tag_to_idx[flat[i + 2]])
                for i in range(0, len(flat), 3)
            )
    return points, tuple(tris)
