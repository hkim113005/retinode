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
sit on the insulating boundary at **z = 0**; the tissue — every cell — is on one
side of it. The analytical field is built by the method of images, so it is
*exactly mirror-symmetric across z = 0*: a cell at +z and its mirror at -z see the
identical field. Either sign is therefore valid analytically. The FEM path,
however, meshes an explicit z >= 0 tissue slab, so the shared Phase-6 convention is
**+z into the tissue, cells at z >= 0** (see docs/electrode-geometry.md). Prefer
z >= 0 for every scene so the same patch drives the analytical and FEM backends
identically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from engine.field import FieldBackend
from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig

from .drive import segment_coords
from .morphology import RGCModel
from .multisite import multisite_threshold
from .placement import place_cell

if TYPE_CHECKING:
    from engine.eval.offtarget import OffTargetSet
    from engine.eval.overlap import OverlapPolicy


def severed_segments(
    model: RGCModel, array: ElectrodeArray, *, eps_um: float = 1.0
) -> frozenset[int]:
    """Segment indices (in ``segment_coords`` order) that lie inside an electrode
    body — the ``displace`` policy's severed compartments. Aligning the overlap
    check to ``segment_coords`` is what lets the index set map straight onto the
    transfer matrix rows and the spike detectors."""
    # Lazy import: overlap lives in engine.eval; a module-level import would form a
    # cable<->eval cycle (same reason population imports offtarget lazily).
    from engine.eval.overlap import check_overlap

    coords, _ = segment_coords(model)
    report = check_overlap(
        array, {"_": [tuple(c) for c in coords]}, near_contact_eps_um=eps_um
    )
    return frozenset(report.inside_compartments("_"))


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
    overlap_policy: OverlapPolicy = "reject",
    overlap_eps_um: float = 1.0,
    amp_min: float = 1.0,
    amp_max: float = 500.0,
    ladder: float = 1.5,
    rel_tol: float = 0.04,
) -> PopulationThresholds:
    """Threshold of the target and each off-target cell under the array's field.

    ``overlap_policy`` governs a cell whose compartments fall inside a 3D electrode
    body (P6 S4): ``"reject"`` (default) raises :class:`OverlapConflict` naming the
    cell; ``"displace"`` severs the interior compartments (no field, no spike
    detection there) and scores the cell on its survivors.
    """
    # Imported lazily: off-target selection is an eval-layer concern, and a
    # module-level import here would form a cable<->eval import cycle.
    from engine.eval.offtarget import OffTargetSet, select_off_targets
    from engine.eval.overlap import OverlapConflict

    off_target_set = off_target_set or OffTargetSet()

    def threshold_of(rgc) -> float | None:
        cell = place_cell(rgc, optic_disc=patch.optic_disc_um)
        deactivated: frozenset[int] = frozenset()
        if any(e.body is not None for e in array.electrodes):
            severed = severed_segments(cell, array, eps_um=overlap_eps_um)
            if severed and overlap_policy == "reject":
                raise OverlapConflict(
                    f"cell {rgc.id!r} has {len(severed)} compartment(s) inside an "
                    f"electrode body; move the cell, resize the electrode, or use the "
                    f"'displace' overlap policy"
                )
            deactivated = severed
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
            deactivated=deactivated,
        ).threshold_uA

    target = patch.target()
    target_threshold = threshold_of(target)

    off_thresholds: dict[str, float] = {}
    for rgc in select_off_targets(patch, array, off_target_set):
        thr = threshold_of(rgc)
        if thr is not None:
            off_thresholds[rgc.id] = thr

    return PopulationThresholds(target.id, target_threshold, off_thresholds)
