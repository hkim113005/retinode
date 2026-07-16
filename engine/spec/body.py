"""3D electrode bodies: parametric primitives that protrude into the tissue.

An electrode with a ``body`` is no longer a flat face on the array plane but a
*solid* the FEM subtracts from the tissue; its conductive surface(s) inject the
current. This module is purely geometric -- dimensions and which surfaces conduct.
The meshing lives in :mod:`engine.field.mesh3d`, and the cable/NEURON biophysics
never sees any of it (Phase-6 D1): a body only changes the field solve.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

# Which surface(s) of a pillar/frustum inject current: the deep tip cap, the
# lateral wall, or both. A hemisphere is always fully conductive.
ConductiveFaces = Literal["tip", "sides", "all"]


@dataclass(frozen=True)
class Hemisphere:
    """A hemispherical electrode of ``radius_um`` protruding into the tissue; its
    whole curved surface conducts. This is the exact known-answer geometry: the
    field outside is a point source, ``V = I / (2 pi sigma r)`` for ``r >= radius``."""

    radius_um: float


@dataclass(frozen=True)
class Cylinder:
    """A cylindrical pillar: ``radius_um`` wide, reaching ``height_um`` into the
    tissue. ``conductive_faces`` selects the injecting surface -- the deep tip cap,
    the side wall, or all of it (an insulated shank is ``"tip"``)."""

    radius_um: float
    height_um: float
    conductive_faces: ConductiveFaces = "all"


@dataclass(frozen=True)
class Frustum:
    """A truncated cone: ``base_radius_um`` at the array plane tapering to
    ``top_radius_um`` at depth ``height_um`` (base > top is a penetrating tip)."""

    base_radius_um: float
    top_radius_um: float
    height_um: float
    conductive_faces: ConductiveFaces = "all"


ElectrodeBody = Hemisphere | Cylinder | Frustum


def body_base_radius_um(body: ElectrodeBody) -> float:
    """The body's lateral radius at the array plane -- used for mesh sizing and the
    aperture-fit check, the way ``radius_um`` is for a flat electrode."""
    if isinstance(body, Hemisphere | Cylinder):
        return body.radius_um
    return body.base_radius_um  # Frustum


def _select_faces_area(tip: float, sides: float, which: ConductiveFaces) -> float:
    return {"tip": tip, "sides": sides, "all": tip + sides}[which]


def body_conductive_area_um2(body: ElectrodeBody) -> float:
    """Area of the conductive surface(s), in square microns -- the denominator for
    charge density in the safety check."""
    if isinstance(body, Hemisphere):
        return 2.0 * math.pi * body.radius_um**2
    if isinstance(body, Cylinder):
        r, h = body.radius_um, body.height_um
        return _select_faces_area(math.pi * r * r, 2.0 * math.pi * r * h, body.conductive_faces)
    # Frustum: lateral (cone-frustum) area + the top cap
    r0, r1, h = body.base_radius_um, body.top_radius_um, body.height_um
    slant = math.hypot(h, r0 - r1)
    return _select_faces_area(math.pi * r1 * r1, math.pi * (r0 + r1) * slant, body.conductive_faces)
