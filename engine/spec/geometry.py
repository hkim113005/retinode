"""ElectrodeArray — the physical geometry. Carries NO current, by construction."""

from __future__ import annotations

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
    pos_um: Vec3                      # center, microns, in the array's frame
    shape: Shape
    size_um: float                   # disk diameter / square edge / hex flat-to-flat
    normal: Vec3 = (0.0, 0.0, 1.0)   # facing direction (toward the retina by default)
    boundary_um: tuple[Vec3, ...] | None = None  # explicit outline, only for shape="poly"


@dataclass(frozen=True)
class ElectrodeArray:
    """An ordered collection of electrodes plus array-level metadata."""

    electrodes: tuple[Electrode, ...]
    frame: str = "patch"             # coordinate convention these positions live in
    schema_version: int = SCHEMA_VERSION

    def ids(self) -> tuple[str, ...]:
        return tuple(e.id for e in self.electrodes)

    def by_id(self, electrode_id: str) -> Electrode:
        for e in self.electrodes:
            if e.id == electrode_id:
                return e
        raise KeyError(electrode_id)
