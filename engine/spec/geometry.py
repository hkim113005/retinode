"""ElectrodeArray: the physical geometry. Carries NO current, by construction."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

from .body import ElectrodeBody, body_base_radius_um, body_conductive_area_um2
from .conventions import SCHEMA_VERSION

Shape = Literal["disk", "square", "hex", "poly"]
Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class ArrayPlacement:
    """How a whole array is planted into the tissue: a rigid pose of every
    electrode. ``rotation_deg`` tilts/rotates the array about its own origin
    (extrinsic rotations about x, then y, then z, in degrees), then ``offset_um``
    translates it. A tilt makes penetrating electrodes enter the tissue at an angle;
    the electrode normals rotate with it.

    Convention (Phase-6 D8): z = 0 is the array plane, +z is into the tissue (the
    default electrode normal direction); the tissue and any FEM-driven cell
    population live at z >= 0. Rotation is a **FEM-tier** concept: the field for a
    tilted body must be FEM, since the analytical tier is an orientation-free point
    source (it sees only ``pos_um``)."""

    offset_um: Vec3 = (0.0, 0.0, 0.0)
    rotation_deg: Vec3 = (0.0, 0.0, 0.0)  # extrinsic x->y->z about the array origin


@dataclass(frozen=True)
class Electrode:
    """A single electrode: where it is and what it looks like, never how much
    current it carries. Current lives in StimConfig, keyed by ``id``."""

    id: str
    pos_um: Vec3  # center, microns, in the array's frame
    shape: Shape
    size_um: float  # disk diameter / square edge / hex flat-to-flat
    normal: Vec3 = (0.0, 0.0, 1.0)  # facing direction (toward the retina by default)
    boundary_um: tuple[Vec3, ...] | None = None  # explicit outline, only for shape="poly"
    body: ElectrodeBody | None = None  # a 3D body (protrudes into tissue); None = flat 2D face


@dataclass(frozen=True)
class ElectrodeArray:
    """An ordered collection of electrodes plus array-level metadata."""

    electrodes: tuple[Electrode, ...]
    frame: str = "patch"  # coordinate convention these positions live in
    placement: ArrayPlacement | None = None  # how the array is planted; None = as-authored
    schema_version: int = SCHEMA_VERSION

    def ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.electrodes)

    def by_id(self, electrode_id: str) -> Electrode:
        for e in self.electrodes:
            if e.id == electrode_id:
                return e
        raise KeyError(electrode_id)


def radius_um(electrode: Electrode) -> float:
    """Effective radius in microns: half the size for disk/square/hex; for a
    polygon, the max distance from center to a boundary vertex (0 if none).

    Shared by overlap validation and the analytical field's near-field
    regularization so the two cannot disagree about an electrode's extent."""
    if electrode.body is not None:  # a 3D body's lateral radius at the array plane
        return body_base_radius_um(electrode.body)
    if electrode.shape == "poly":
        if not electrode.boundary_um:
            return 0.0
        return max(math.dist(electrode.pos_um, b) for b in electrode.boundary_um)
    return electrode.size_um / 2.0


def electrode_outline(electrode: Electrode) -> tuple[tuple[float, float], ...] | None:
    """The electrode face outline as (x, y) vertices on the z=0 plane, or ``None``
    for a disk (which has no polygonal outline). Squares and hexes are derived from
    ``size_um`` about ``pos_um``; polygons use the explicit ``boundary_um``. This is
    the single source the FEM mesh imprints and any renderer would draw, so the
    shape can never disagree between backends."""
    x, y, _ = electrode.pos_um
    if electrode.shape == "disk":
        return None
    if electrode.shape == "square":
        h = electrode.size_um / 2.0
        return ((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h))
    if electrode.shape == "hex":  # size_um is the flat-to-flat width
        r = electrode.size_um / math.sqrt(3.0)  # circumradius; 2*apothem = size
        return tuple(
            (
                x + r * math.cos(math.radians(30 + 60 * k)),
                y + r * math.sin(math.radians(30 + 60 * k)),
            )
            for k in range(6)
        )
    # poly
    if not electrode.boundary_um:
        return None
    return tuple((b[0], b[1]) for b in electrode.boundary_um)


def _polygon_area_um2(verts: tuple[tuple[float, float], ...]) -> float:
    """Unsigned area of a simple polygon (shoelace), in square microns."""
    n = len(verts)
    s = 0.0
    for i in range(n):
        x1, y1 = verts[i]
        x2, y2 = verts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def electrode_area_um2(electrode: Electrode) -> float:
    """Geometric area of the electrode face, in square microns. Shared by the
    safety charge-density check and the FEM mesh's electrode-surface matching, so
    the two cannot disagree about an electrode's area. For a 3D body this is the
    conductive-surface area."""
    if electrode.body is not None:
        return body_conductive_area_um2(electrode.body)
    if electrode.shape == "disk":
        return math.pi * (electrode.size_um / 2.0) ** 2
    if electrode.shape == "square":
        return electrode.size_um**2
    if electrode.shape == "hex":  # size_um is the flat-to-flat width
        return (math.sqrt(3.0) / 2.0) * electrode.size_um**2
    outline = electrode_outline(electrode)  # poly
    return _polygon_area_um2(outline) if outline else 0.0


Mat3 = tuple[Vec3, Vec3, Vec3]
_IDENTITY3: Mat3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def rotation_matrix(rotation_deg: Vec3) -> Mat3:
    """The 3x3 rotation for ``rotation_deg``: extrinsic rotations about x, then y,
    then z (``R = Rz @ Ry @ Rx``), in degrees. Pure Python (no numpy) so the spec layer
    stays dependency-free; the field/overlap layers apply it to positions and, via
    its transpose, map a world point into a body's local frame."""
    ax, ay, az = (math.radians(a) for a in rotation_deg)
    cx, sx, cy, sy, cz, sz = (
        math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az),
    )
    # R = Rz @ Ry @ Rx, expanded.
    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )


def apply_matrix(m: Mat3, v: Vec3) -> Vec3:
    """Multiply the 3x3 ``m`` by the 3-vector ``v``."""
    return (
        m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
        m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
        m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2],
    )


def transpose3(m: Mat3) -> Mat3:
    """Transpose of a 3x3 (the inverse of a rotation), which maps world into local."""
    return (
        (m[0][0], m[1][0], m[2][0]),
        (m[0][1], m[1][1], m[2][1]),
        (m[0][2], m[1][2], m[2][2]),
    )


def placement_rotation(array: ElectrodeArray) -> Mat3:
    """The array placement's rotation matrix (identity when unposed or untilted)."""
    if array.placement is None:
        return _IDENTITY3
    return rotation_matrix(array.placement.rotation_deg)


def apply_placement(array: ElectrodeArray) -> tuple[Electrode, ...]:
    """The array's electrodes posed by its :class:`ArrayPlacement`: each position
    (and any polygon outline) is rotated about the array origin then translated by
    the offset, and each electrode ``normal`` is rotated (a tilt reorients the
    faces). No placement returns the electrodes unchanged. This is the concrete
    positioned geometry the FEM mesh builds; the placement is part of the array's
    hash, so a re-posed array keys distinctly (provenance).

    The electrode ``body`` is left as authored (its primitives are defined in the
    body-local frame); the field mesh and the overlap check orient it with the same
    rotation, read via :func:`placement_rotation`."""
    placement = array.placement
    if placement is None:
        return array.electrodes
    ox, oy, oz = placement.offset_um
    r = rotation_matrix(placement.rotation_deg)

    def pose(p: Vec3) -> Vec3:
        rx, ry, rz = apply_matrix(r, p)
        return (rx + ox, ry + oy, rz + oz)

    placed: list[Electrode] = []
    for e in array.electrodes:
        boundary = None if e.boundary_um is None else tuple(pose(b) for b in e.boundary_um)
        placed.append(
            replace(
                e,
                pos_um=pose(e.pos_um),
                normal=apply_matrix(r, e.normal),  # rotate only (a direction, not a point)
                boundary_um=boundary,
            )
        )
    return tuple(placed)
