"""Trajectory spread across a geometry sweep: the honest error bar on a candidate.

An epiretinal threshold depends strongly on the ascending axon, and the true path of
any one cell's axon is *unknown*. ``engine.cable.trajectories`` answers that for one
cell — sample K plausible paths, report the spread of thresholds. This lifts it to a
geometry sweep, which is the lift ``trajectories.py`` explicitly deferred ("full
trajectory × population sweeps are deliberately a Phase-5 concern").

The number this produces is **epistemic**: it says "given we do not know where this
cell's axon runs, its threshold could be anywhere in this band" — not "the surgeon
may misplace the array", which is a different (also interesting, also unbuilt)
question about placement.

Scoped to the **target** cell by design. The whisker rides the target threshold —
the number a candidate is ranked on — and spreading the whole population would
multiply the cost by the cell count for a number nothing displays.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING

from engine.cable.trajectories import trajectory_spread

from .geometry import ArrayGeometry, build_array

if TYPE_CHECKING:  # pragma: no cover
    from engine.field import FieldBackend
    from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig

# Same shape as ``geometry_sweep``'s: a protocol is a function of the array, because
# a config's weight map keys are THAT array's electrode ids. A config built for one
# geometry is meaningless against another.
ConfigFactory = Callable[["ElectrodeArray"], "list[StimConfig]"]


def geometry_trajectory_spread(
    geometries: Iterable[ArrayGeometry],
    patch: RetinalPatch,
    config_factory: ConfigFactory,
    conductivity: ConductivityModel,
    *,
    k: int = 3,
    jitter_deg: float = 15.0,
    backend: FieldBackend | None = None,
) -> dict[tuple[float, float], float | None]:
    """Std of the target threshold over K axon trajectories, per geometry.

    Keyed by ``(diameter_um, pitch_um)`` — the same identity the study's points carry.
    A value is ``None`` when the target never fired on enough trajectories to have a
    spread; callers must render that as *absent*, never as zero. A confident-looking
    ``±0.0`` on a design nobody could measure is worse than no whisker at all.

    Cost: K threshold searches per geometry, on top of the sweep's own. K=1 is a
    single search and yields no spread (std of one sample is not a thing).

    The spread is measured on the protocol's **first** config, matching the whisker's
    meaning: an error bar on the threshold a candidate is ranked by, not on every
    config a multi-config protocol might contain.
    """
    out: dict[tuple[float, float], float | None] = {}
    target = patch.target()
    for g in geometries:
        array = build_array(g)
        configs = config_factory(array)
        if not configs:
            out[(g.diameter_um, g.pitch_um)] = None
            continue
        spread = trajectory_spread(
            target,
            array,
            configs[0],
            conductivity,
            optic_disc=patch.optic_disc_um,
            k=k,
            jitter_deg=jitter_deg,
            backend=backend,
        )
        # a std needs at least two samples that actually fired
        out[(g.diameter_um, g.pitch_um)] = spread.std_uA if spread.n >= 2 else None
    return out
