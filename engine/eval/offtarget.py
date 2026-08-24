"""The off-target set: which non-target cells a selectivity score is measured against.

This is an explicit, recorded modeling choice. It shapes the SOW more than
almost anything else, so it is a first-class, editable object rather than a
buried constant. A cell is off-target if its soma is within ``soma_radius_um`` of the
target soma, or (when ``axon_proximity_um`` is set) its axon passes within that
distance of any electrode. ``max_soma_count`` optionally keeps only the nearest N.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.spec import ElectrodeArray, RetinalPatch
from engine.spec.conventions import SCHEMA_VERSION
from engine.spec.patch import RGC


@dataclass(frozen=True)
class OffTargetSet:
    soma_radius_um: float = 120.0
    max_soma_count: int | None = None
    axon_proximity_um: float | None = 30.0  # None = ignore axons
    schema_version: int = SCHEMA_VERSION


def _axon_near_array(cell: RGC, array: ElectrodeArray, proximity_um: float) -> bool:
    if not cell.axon_um or not array.electrodes:
        return False
    return any(
        math.dist(pt, e.pos_um) <= proximity_um for pt in cell.axon_um for e in array.electrodes
    )


def select_off_targets(
    patch: RetinalPatch,
    array: ElectrodeArray,
    off_target_set: OffTargetSet,
) -> tuple[RGC, ...]:
    """The off-target cells of the patch under this off-target definition."""
    target = patch.target()
    selected: list[RGC] = []
    for cell in patch.cells:
        if cell.id == patch.target_id:
            continue
        near_soma = math.dist(cell.soma_um, target.soma_um) <= off_target_set.soma_radius_um
        near_axon = off_target_set.axon_proximity_um is not None and _axon_near_array(
            cell, array, off_target_set.axon_proximity_um
        )
        if near_soma or near_axon:
            selected.append(cell)

    if off_target_set.max_soma_count is not None:
        selected.sort(key=lambda c: math.dist(c.soma_um, target.soma_um))
        selected = selected[: off_target_set.max_soma_count]
    return tuple(selected)
