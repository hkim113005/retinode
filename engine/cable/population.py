"""Per-cell thresholds over a population (S6c).

Places the target and its off-target cells (from the patch + an OffTargetSet) and
finds each cell's activation threshold under the array's field, using multi-site
activation (a spike anywhere counts — so an off-target's axon of passage firing
makes it activated). This is the per-cell data the evaluator (S7) turns into the
selective operating window.

Cells do not interact electrically in this model, so each threshold is an
independent search. One nominal axon trajectory per cell here; the trajectory
distribution (spread) is trajectories.py, and full trajectory×population sweeps
are a Phase-5 concern.

Coordinate convention (matters for the half-space field): the array/electrodes
sit on the insulating boundary at **z = 0** and the tissue — every cell — is
**below, at z < 0**. Placing a cell above the boundary (z > 0) mirrors it onto an
electrode's method-of-images source and yields a spurious field.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.field import FieldBackend
from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig

from .multisite import multisite_threshold
from .placement import place_cell

if TYPE_CHECKING:
    from engine.eval.offtarget import OffTargetSet


@dataclass(frozen=True)
class PopulationThresholds:
    target_id: str
    target_threshold_uA: float | None
    off_target_thresholds_uA: dict[str, float]  # id -> threshold (cells that fired)


def population_thresholds(
    patch: RetinalPatch,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    off_target_set: OffTargetSet | None = None,
    backend: FieldBackend | None = None,
    amp_min: float = 1.0,
    amp_max: float = 500.0,
    ladder: float = 1.5,
    rel_tol: float = 0.04,
) -> PopulationThresholds:
    """Threshold of the target and each off-target cell under the array's field."""
    # Imported lazily: off-target selection is an eval-layer concern, and a
    # module-level import here would form a cable<->eval import cycle.
    from engine.eval.offtarget import OffTargetSet, select_off_targets

    off_target_set = off_target_set or OffTargetSet()

    def threshold_of(rgc) -> float | None:
        cell = place_cell(rgc, optic_disc=patch.optic_disc_um)
        return multisite_threshold(
            cell,
            array,
            config,
            conductivity,
            backend=backend,
            amp_min=amp_min,
            amp_max=amp_max,
            ladder=ladder,
            rel_tol=rel_tol,
        ).threshold_uA

    target = patch.target()
    target_threshold = threshold_of(target)

    off_thresholds: dict[str, float] = {}
    for rgc in select_off_targets(patch, array, off_target_set):
        thr = threshold_of(rgc)
        if thr is not None:
            off_thresholds[rgc.id] = thr

    return PopulationThresholds(target.id, target_threshold, off_thresholds)
