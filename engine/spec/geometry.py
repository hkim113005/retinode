"""ElectrodeArray — the physical geometry. Carries NO current, by construction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from .conventions import SCHEMA_VERSION

Shape = Literal["disk", "square", "hex", "poly"]
Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class Electrode:
    """A single electrode: where it is and what it looks like — never how much
    current it carries. Current lives in StimConfig, keyed by ``id``."""

    id: str
    pos_um: Vec3  # center, microns, in the array's frame
    shape: Shape
    size_um: float  # disk diameter / square edge / hex flat-to-flat
    normal: Vec3 = (0.0, 0.0, 1.0)  # facing direction (toward the retina by default)
    boundary_um: tuple[Vec3, ...] | None = None  # explicit outline, only for shape="poly"


@dataclass(frozen=True)
class ElectrodeArray:
    """An ordered collection of electrodes plus array-level metadata."""

    electrodes: tuple[Electrode, ...]
    frame: str = "patch"  # coordinate convention these positions live in
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
    the two cannot disagree about an electrode's area."""
    if electrode.shape == "disk":
        return math.pi * (electrode.size_um / 2.0) ** 2
    if electrode.shape == "square":
        return electrode.size_um**2
    if electrode.shape == "hex":  # size_um is the flat-to-flat width
        return (math.sqrt(3.0) / 2.0) * electrode.size_um**2
    outline = electrode_outline(electrode)  # poly
    return _polygon_area_um2(outline) if outline else 0.0
