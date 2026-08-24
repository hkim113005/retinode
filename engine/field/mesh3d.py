"""3D electrode bodies in the FEM mesh: build the solid, tag its surfaces (P6 S2).

The tissue domain is the slab *minus* the electrode body, a boolean cut done in
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
import re

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
        # The primitives above are already in microns; a CAD file is in whatever unit
        # it declares. Scale the imported solid so the MESHED geometry matches the
        # dimensions load_cad_body recorded. Otherwise the body's metadata says 5 um
        # while the solve cuts a 5000 um hole out of the tissue.
        cad_scale = cad_unit_scale_um(body.cad_path)
        if cad_scale != 1.0:
            occ.dilate([(3, solid)], 0.0, 0.0, 0.0, cad_scale, cad_scale, cad_scale)
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


# Every length in this engine is microns (spec/conventions.py). A STEP/IGES file
# DECLARES its own unit in its header, and almost every CAD package exports
# millimetres by default, so its raw coordinates are not microns until converted.
#
# gmsh has a Geometry.OCCTargetUnit option, but it is global process state applied
# deep inside OCC's STEP reader, and it proved order-dependent: with two loads in one
# process only one of them converted, depending on which ran first. A silent 1000x
# scale error is exactly what this is meant to prevent, so the unit is read from the
# file and applied explicitly here instead. Scaling the SHAPE (occ.dilate) rather than
# the measurements keeps the bounding box, the face areas and the baked triangulation
# consistent with one another for free.
_UM_PER: dict[str, float] = {
    "METRE": 1.0e6,
    "MILLI": 1.0e3,
    "CENTI": 1.0e4,
    "MICRO": 1.0,
    "NANO": 1.0e-3,
}


def cad_unit_scale_um(cad_path: str) -> float:
    """Microns per file unit, from the CAD's own declared length unit.

    A BREP declares nothing (it is a raw geometry dump), and neither does a file whose
    header we cannot read, so both fall back to 1.0: their numbers are taken as
    microns. That assumption is the format's limitation, not a guess we can improve on.
    """
    if not cad_path.lower().endswith((".step", ".stp", ".iges", ".igs")):
        return 1.0
    try:
        with open(cad_path, encoding="utf-8", errors="replace") as fh:
            head = fh.read(200_000)  # the header + unit context live near the top
    except OSError:
        return 1.0
    # e.g. "( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) )". The prefix is
    # optional ("SI_UNIT($,.METRE.)" is a bare metre).
    m = re.search(r"SI_UNIT\s*\(\s*(?:\.(\w+)\.|\$)\s*,\s*\.METRE\.\s*\)", head)
    if m is None:
        return 1.0
    return _UM_PER.get((m.group(1) or "METRE").upper(), 1.0)

# A retinal electrode is a micron-scale object and the FEM domain is sized in
# hundreds of microns. A body larger than this is not a design choice, it is a unit
# error that would otherwise sail through and produce a physically meaningless
# solve, so it is refused with an explanation rather than scored.
MAX_CAD_EXTENT_UM = 2000.0


def load_cad_body(
    cad_path: str, *, conductive_faces: str = "all", overlap_mesh_size_um: float | None = None
) -> CadBody:
    """Read a STEP/BREP solid and build a :class:`~engine.spec.body.CadBody`: hash
    its content (the geometric identity, for provenance), measure its bounding
    radius/height and its exposed surface area (split tip/sides), and bake a coarse
    triangulated surface so the pure-Python overlap check can test point-in-solid
    exactly without gmsh (P6 S9). The CAD's origin is taken as the electrode's base
    on the array plane; the exposed area excludes the z=0 base face (the substrate
    opening, not a conductive surface). Requires gmsh (the fem env).

    **Units.** A STEP/IGES file declares its own length unit, and CAD packages export
    millimetres by default. Those raw coordinates were previously taken as microns,
    so a solid authored at true implant scale came in 1000x too small, silently and
    with no warning, producing a plausible-looking but meaningless score. The declared
    unit is now honoured: :func:`cad_unit_scale_um` reads it from the file header and
    the geometry is scaled here. A **BREP** carries no unit (it is a raw geometry
    dump), so its numbers are still read as microns. That is the only remaining
    assumption, and it is the format's own limitation.

    If the result is implausibly large for a retina, this raises rather than solving:
    a wrong declared unit is far likelier than a millimetre-scale retinal electrode.
    """
    import gmsh

    with open(cad_path, "rb") as f:
        content_hash = hashlib.sha256(f.read()).hexdigest()

    scale = cad_unit_scale_um(cad_path)

    gmsh.initialize()
    try:
        gmsh.model.add("cad")
        occ = gmsh.model.occ
        solid = occ.importShapes(cad_path)[0]
        occ.synchronize()
        # Everything below is measured in the FILE's own unit and converted at the end
        # (lengths x scale, areas x scale^2). Scaling the OCC shape in place with
        # occ.dilate was tried first and gave a bounding box inflated by sqrt(3);
        # measure-then-convert is arithmetic we control.
        xmin, ymin, zmin, xmax, ymax, zmax = occ.getBoundingBox(*solid)
        bounding_radius = 0.5 * max(xmax - xmin, ymax - ymin) * scale
        bounding_height = (zmax - zmin) * scale
        extent = max(bounding_radius, bounding_height)
        if extent > MAX_CAD_EXTENT_UM:
            raise ValueError(
                f"the CAD solid measures {2 * bounding_radius:.4g} x "
                f"{bounding_height:.4g} um after unit conversion, which is far larger "
                f"than a retinal electrode (cap {MAX_CAD_EXTENT_UM:.0f} um). The usual "
                "cause is the file's declared length unit: this engine works in "
                "microns, and a solid drawn as '5 x 30' in a millimetre file is "
                "5000 x 30000 um. Re-export it at micron scale, or scale the geometry "
                "down before uploading."
            )
        # Sum the exposed area, and split it into a deep "tip" and lateral "sides"
        # by centroid depth (the same 0.75*height threshold the mesh uses to classify
        # cavity walls, so the load-time areas match the meshed conductive surfaces).
        # The z=0 base face is the substrate opening, not a conductive surface.
        tip_area = 0.0
        sides_area = 0.0
        for _dim, s in gmsh.model.getBoundary([solid], combined=True, oriented=False):
            cz = occ.getCenterOfMass(2, s)[2]
            if abs(cz * scale) <= 1e-6:
                continue  # the z=0 base
            area = occ.getMass(2, s) * scale * scale
            cz *= scale
            if cz >= 0.75 * bounding_height:
                tip_area += area
            else:
                sides_area += area
        # A coarse surface triangulation of the whole closed solid (base included, so
        # the ray-parity point-in-solid test is watertight) for exact overlap.
        # meshed in file units, so the target size must come back out of microns
        size = (overlap_mesh_size_um or max(bounding_radius, bounding_height) / 6.0) / scale
        points, tris = _surface_triangulation(gmsh, size)
        if scale != 1.0:
            points = tuple((x * scale, y * scale, z * scale) for (x, y, z) in points)
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
    """Surface-mesh the loaded solid at ``size_um`` and return ``(points, tris)`` for
    the exact overlap proxy: node coordinates (microns) and triangles indexing them.
    The model already holds the synchronized solid."""
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
