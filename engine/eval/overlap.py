"""Cell <-> electrode-body overlap: detect and resolve conflicts (P6 S4).

A physical electrode is solid metal; tissue and neurons cannot occupy its volume.
So when a 3D electrode body is planted into the tissue, a cell compartment falling
*inside* the body is a **geometry conflict**, not a field to compute — and a
compartment pressed right against a conductive surface (**near-contact**) is where
the standard passive-probe field approximation (the neuron does not perturb the
field) starts to fray.

This module detects both from pure geometry -- ``point_in_body`` /
``surface_distance_um`` in :mod:`engine.spec.body`, the same solids the mesh cuts
-- and applies the policy (Phase-6 D9):

- **reject** (default): raise on any conflict, naming the cell / electrode /
  compartment, so a scene that puts a neuron inside metal fails loudly.
- **displace**: report which compartments to deactivate (they lie in the metal, so
  the inserted electrode has displaced or severed the cell there); the cable model
  then runs on the surviving compartments -- still no change to NEURON itself, only
  to *which* compartments are simulated.

Nothing here touches NEURON or the field solve; it is geometry + a policy decision.
``evaluate`` / ``population_thresholds`` consume that decision: they recompute the
overlap in the model's ``segment_coords`` order (so the indices align with the
transfer-matrix rows) and either raise on ``reject`` or, on ``displace``, sever the
interior compartments from both the field solve and spike detection. This module
stays NEURON-free; the wiring lives in :mod:`engine.cable.population`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from engine.spec import ElectrodeArray
from engine.spec.body import point_in_body, surface_distance_um
from engine.spec.geometry import apply_placement

OverlapPolicy = Literal["reject", "displace"]

# A compartment is (x, y, z) microns; a cell is its ordered compartment centres.
Point = tuple[float, float, float]


class OverlapConflict(Exception):
    """A neuron compartment lies inside an electrode body -- a geometry conflict a
    ``reject`` policy refuses rather than compute a meaningless field for."""


@dataclass(frozen=True)
class CompartmentFlag:
    """One (cell, electrode, compartment) that overlaps or nearly touches a body."""

    cell_id: str
    electrode_id: str
    compartment: int  # index into the cell's compartment list
    inside: bool  # inside the body volume -> a conflict
    near_contact: bool  # just outside, within eps of a surface -> passive-probe caveat


@dataclass(frozen=True)
class OverlapReport:
    """Every flagged compartment for a scene, plus the near-contact tolerance used."""

    flags: tuple[CompartmentFlag, ...]
    near_contact_eps_um: float

    @property
    def conflicts(self) -> tuple[CompartmentFlag, ...]:
        return tuple(f for f in self.flags if f.inside)

    @property
    def near_contacts(self) -> tuple[CompartmentFlag, ...]:
        return tuple(f for f in self.flags if f.near_contact and not f.inside)

    @property
    def has_conflict(self) -> bool:
        return any(f.inside for f in self.flags)

    def inside_compartments(self, cell_id: str) -> set[int]:
        """Compartments of ``cell_id`` that lie inside some electrode body."""
        return {f.compartment for f in self.flags if f.cell_id == cell_id and f.inside}


def check_overlap(
    array: ElectrodeArray,
    cell_compartments: Mapping[str, Sequence[Point]],
    *,
    near_contact_eps_um: float = 1.0,
) -> OverlapReport:
    """Flag every compartment that lies inside an electrode body (a conflict) or
    within ``near_contact_eps_um`` of one (near-contact). The array's placement is
    applied first, so bodies are tested at their planted positions. Flat electrodes
    (no body) never conflict."""
    bodies = [e for e in apply_placement(array) if e.body is not None]
    flags: list[CompartmentFlag] = []
    for cell_id, compartments in cell_compartments.items():
        for i, (px, py, pz) in enumerate(compartments):
            for e in bodies:
                dx, dy, dz = px - e.pos_um[0], py - e.pos_um[1], pz - e.pos_um[2]
                inside = point_in_body(e.body, dx, dy, dz)  # type: ignore[arg-type]
                near = not inside and surface_distance_um(e.body, dx, dy, dz) <= near_contact_eps_um  # type: ignore[arg-type]
                if inside or near:
                    flags.append(CompartmentFlag(cell_id, e.id, i, inside, near))
    return OverlapReport(tuple(flags), near_contact_eps_um)


def resolve_overlap(report: OverlapReport, policy: OverlapPolicy) -> dict[str, set[int]]:
    """Apply the overlap ``policy`` to a report.

    - ``"reject"``: raise :class:`OverlapConflict` on the first conflict.
    - ``"displace"``: return ``{cell_id: {compartment indices to deactivate}}`` --
      the compartments inside the metal, which the caller drops before simulating.

    No conflict -> ``{}`` for either policy (near-contacts are flagged, not acted on)."""
    if not report.has_conflict:
        return {}
    if policy == "reject":
        c = report.conflicts[0]
        raise OverlapConflict(
            f"cell {c.cell_id!r} compartment {c.compartment} lies inside electrode "
            f"{c.electrode_id!r}'s body; move the cell, resize the electrode, or use the "
            f"'displace' policy to deactivate the interior compartments"
        )
    dropped: dict[str, set[int]] = {}
    for f in report.conflicts:
        dropped.setdefault(f.cell_id, set()).add(f.compartment)
    return dropped
