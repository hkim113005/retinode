"""Parametric array geometry — the axis a geometry sweep moves along (P5 S1).

A geometry study varies the *array*, not just the stimulus: electrode diameter,
center-to-center pitch, and lattice arrangement. This module turns those few
numbers into a canonical :class:`~engine.spec.ElectrodeArray`, deterministically,
so a sweep can enumerate geometries, hash them, and cache their fields.

``ArrayGeometry`` is a frozen (hashable) description; ``build_array`` is a pure
function of it. Electrodes fill a disk of radius ``aperture_um`` on the z=0 plane,
on a square (``"grid"``) or hexagonal (``"hex"``) lattice with nearest-neighbour
spacing ``pitch_um``. ``pitch_um >= diameter_um`` is required so the disks never
overlap — the same condition ``engine.spec.validate`` enforces, caught here early
with a clear error rather than as a downstream overlap problem.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from engine.spec import Cylinder, Electrode, ElectrodeArray, ElectrodeBody, Shape

Arrangement = Literal["grid", "hex"]

_APERTURE_ATOL_UM = 1e-9  # include a centre sitting exactly on the aperture circle


@dataclass(frozen=True)
class ArrayGeometry:
    """A parametric electrode array: what a geometry sweep iterates over.

    Frozen, so it hashes and compares by value — a geometry is a stable key. The
    array itself is produced by :func:`build_array`; two equal ``ArrayGeometry``
    always build the identical array (same ids, same positions).
    """

    diameter_um: float  # electrode size (disk diameter / square edge)
    pitch_um: float  # nearest-neighbour center-to-center spacing
    arrangement: Arrangement  # "grid" (square lattice) or "hex" (hexagonal)
    aperture_um: float  # electrode centers fill a disk of this radius about the origin
    shape: Shape = "disk"
    body: ElectrodeBody | None = None  # a 3D body applied to every electrode (P6 S5)

    def label(self) -> str:
        """Short human label for logs/plots (not a cache key — the array hash is)."""
        tag = f"/{type(self.body).__name__}" if self.body is not None else ""
        return (
            f"{self.arrangement}/d{self.diameter_um:g}/p{self.pitch_um:g}/"
            f"a{self.aperture_um:g}{tag}"
        )


def build_array(geometry: ArrayGeometry, *, id_prefix: str = "e") -> ElectrodeArray:
    """Build the canonical :class:`ElectrodeArray` for ``geometry``.

    Electrode ids are ``{id_prefix}0..{n-1}`` in a deterministic order (sorted by
    y then x), so the mapping is a pure, repeatable function of the geometry. When
    the geometry carries a ``body``, every electrode is that 3D body (a uniform
    penetrating array), so a geometry sweep can vary the body's parameters too.
    """
    validate_geometry(geometry)
    points = _lattice_points(geometry)
    electrodes = tuple(
        Electrode(
            id=f"{id_prefix}{i}",
            pos_um=(x, y, 0.0),
            shape=geometry.shape,
            size_um=geometry.diameter_um,
            body=geometry.body,
        )
        for i, (x, y) in enumerate(points)
    )
    return ElectrodeArray(electrodes=electrodes)


def validate_geometry(geometry: ArrayGeometry) -> None:
    """Cheap sanity checks — positive sizes, a real arrangement, and no electrode
    overlap (``pitch >= diameter``) — raised here rather than surfacing later."""
    if geometry.diameter_um <= 0:
        raise ValueError("diameter_um must be positive")
    if geometry.pitch_um <= 0:
        raise ValueError("pitch_um must be positive")
    if geometry.aperture_um < 0:
        raise ValueError("aperture_um must be non-negative")
    if geometry.arrangement not in ("grid", "hex"):
        raise ValueError(f"unknown arrangement {geometry.arrangement!r}")
    if geometry.pitch_um < geometry.diameter_um:
        raise ValueError(
            f"pitch_um ({geometry.pitch_um}) < diameter_um ({geometry.diameter_um}): "
            "electrodes would overlap"
        )


def geometry_grid(
    *,
    diameters_um: list[float],
    pitches_um: list[float],
    arrangement: Arrangement,
    aperture_um: float,
    shape: Shape = "disk",
) -> list[ArrayGeometry]:
    """The diameter × pitch Cartesian product, dropping combos where
    ``pitch < diameter`` (which would overlap). The parameter list a P5 S2
    geometry sweep enumerates."""
    out: list[ArrayGeometry] = []
    for d in diameters_um:
        for p in pitches_um:
            if p >= d:
                out.append(ArrayGeometry(d, p, arrangement, aperture_um, shape))
    return out


def pillar_geometry_grid(
    *,
    diameters_um: list[float],
    pitches_um: list[float],
    heights_um: list[float],
    arrangement: Arrangement,
    aperture_um: float,
) -> list[ArrayGeometry]:
    """A 3D geometry grid: the diameter × pitch × **height** product, each a uniform
    array of **penetrating cylinder** electrodes (radius = diameter/2, the given
    height). Feeds a P5 geometry sweep / surrogate so 3D insertion designs can be
    explored the same way flat layouts are. Overlapping (pitch < diameter) combos
    are dropped."""
    out: list[ArrayGeometry] = []
    for d in diameters_um:
        for p in pitches_um:
            if p < d:
                continue
            for h in heights_um:
                body: ElectrodeBody = Cylinder(radius_um=d / 2.0, height_um=h)
                out.append(ArrayGeometry(d, p, arrangement, aperture_um, "disk", body))
    return out


def _lattice_points(geometry: ArrayGeometry) -> list[tuple[float, float]]:
    """Lattice centers within the aperture disk, sorted (y, then x) for stable ids."""
    pitch = geometry.pitch_um
    reach = geometry.aperture_um + _APERTURE_ATOL_UM
    points: list[tuple[float, float]] = []

    if geometry.arrangement == "grid":
        n = math.ceil(geometry.aperture_um / pitch) if pitch else 0
        for j in range(-n, n + 1):
            for i in range(-n, n + 1):
                x, y = i * pitch, j * pitch
                if math.hypot(x, y) <= reach:
                    points.append((x, y))
    else:  # hex: rows spaced pitch*sqrt(3)/2, odd rows offset by pitch/2
        row_dy = pitch * math.sqrt(3.0) / 2.0
        nj = math.ceil(geometry.aperture_um / row_dy) if row_dy else 0
        ni = math.ceil(geometry.aperture_um / pitch) + 1 if pitch else 0
        for j in range(-nj, nj + 1):
            y = j * row_dy
            x0 = (pitch / 2.0) if (j % 2) else 0.0
            for i in range(-ni, ni + 1):
                x = i * pitch + x0
                if math.hypot(x, y) <= reach:
                    points.append((x, y))

    # round the sort key so float noise cannot reorder ids across runs/platforms
    points.sort(key=lambda p: (round(p[1], 6), round(p[0], 6)))
    return points
