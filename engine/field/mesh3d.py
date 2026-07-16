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

from engine.spec.body import CadBody, Cylinder, Frustum, Hemisphere


def add_body_solid(occ, electrode):  # noqa: ANN001 - occ is the gmsh OCC kernel
    """Create the electrode's 3D body as an OCC solid at ``pos_um``, protruding
    into z > 0. Cutting the (z >= 0) tissue box by this solid leaves the cavity
    whose walls inject current."""
    body = electrode.body
    x, y, _ = electrode.pos_um
    if isinstance(body, Hemisphere):
        # A full sphere centred on the plane; its z<0 half is outside the tissue
        # box, so the cut removes exactly the z>=0 hemisphere.
        return occ.addSphere(x, y, 0.0, body.radius_um)
    if isinstance(body, Cylinder):
        return occ.addCylinder(x, y, 0.0, 0.0, 0.0, body.height_um, body.radius_um)
    if isinstance(body, Frustum):
        return occ.addCone(
            x, y, 0.0, 0.0, 0.0, body.height_um, body.base_radius_um, body.top_radius_um
        )
    if isinstance(body, CadBody):
        # Import the CAD solid (its origin is the electrode base) and translate it
        # to the electrode's position on the array plane.
        dimtags = occ.importShapes(body.cad_path)
        occ.translate(dimtags, x, y, 0.0)
        return dimtags[0][1]
    raise TypeError(f"unsupported electrode body: {type(body).__name__}")


def classify_cavity_surfaces(occ, electrode, wall_surfs):  # noqa: ANN001
    """Split an electrode's cavity-wall surfaces into ``(conductive, insulated)``
    per its body's ``conductive_faces``. A hemisphere and an imported CAD body are
    fully conductive (the whole exposed surface injects); for a cylinder/frustum the
    deep **tip** cap (centroid near z=height) and the lateral **side** wall (centroid
    mid-depth) are separated by centroid depth, and the selector picks which conduct."""
    body = electrode.body
    if isinstance(body, Hemisphere | CadBody):
        return list(wall_surfs), []

    height = body.height_um
    tip: list[int] = []
    sides: list[int] = []
    for surf in wall_surfs:
        _cx, _cy, cz = occ.getCenterOfMass(2, surf)
        (tip if cz >= 0.75 * height else sides).append(surf)

    which = body.conductive_faces
    if which == "tip":
        return tip, sides
    if which == "sides":
        return sides, tip
    return tip + sides, []  # "all"


def load_cad_body(cad_path: str, *, conductive_faces: str = "all") -> CadBody:
    """Read a STEP/BREP solid and build a :class:`~engine.spec.body.CadBody`: hash
    its content (the geometric identity, for provenance), and measure its bounding
    radius/height and its exposed surface area (for mesh sizing, the overlap check,
    and the safety charge density). The CAD's origin is taken as the electrode's
    base on the array plane; the exposed area excludes the z=0 base face (that is
    the substrate opening, not a conductive surface). Requires gmsh (the fem env)."""
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
        faces = gmsh.model.getBoundary([solid], combined=True, oriented=False)
        surface_area = sum(
            occ.getMass(2, s) for (_dim, s) in faces if abs(occ.getCenterOfMass(2, s)[2]) > 1e-6
        )
    finally:
        gmsh.finalize()

    return CadBody(
        cad_path=cad_path,
        content_hash=content_hash,
        bounding_radius_um=bounding_radius,
        bounding_height_um=bounding_height,
        surface_area_um2=surface_area,
        conductive_faces=conductive_faces,  # type: ignore[arg-type]
    )
