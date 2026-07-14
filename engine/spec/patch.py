"""RetinalPatch — the population of cells being stimulated, and the target."""

from __future__ import annotations

from dataclasses import dataclass

from .conventions import SCHEMA_VERSION

Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class RGC:
    """A retinal ganglion cell: a soma, an optional dendritic field, and an
    axon path toward the optic disc.

    The axon matters as much as the soma: an axon of passage crossing the patch
    can be activated and produce a smeared, non-focal percept, so it is the
    central off-target in the selectivity problem. It is modeled as an ordered
    path of compartment centers, populated when a trajectory is assigned (Phase 1).
    """

    id: str
    cell_type: str  # e.g. "parasol_on", "midget_off"
    soma_um: Vec3
    dendrite_diam_um: float | None = None
    axon_um: tuple[Vec3, ...] = ()  # ordered path, soma -> optic disc


@dataclass(frozen=True)
class RetinalPatch:
    """The cell population plus the designated target cell.

    Note: the index that maps field query points to per-cell compartments is
    *derived* at run time by the field/cable layers from these positions — it is
    not stored here, so the spec stays a pure, hashable description.
    """

    cells: tuple[RGC, ...]
    target_id: str
    optic_disc_um: Vec3 | None = None  # where axons head; sets axon direction
    frame: str = "patch"
    schema_version: int = SCHEMA_VERSION

    def target(self) -> RGC:
        for c in self.cells:
            if c.id == self.target_id:
                return c
        raise KeyError(self.target_id)
