"""Activation versus amplitude: who fires, at what current.

The threshold search already probes ~20 amplitudes per cell and throws every one
away, keeping only the crossing (``engine.cable.threshold``). This sweeps a *stated*
amplitude grid instead and keeps the whole answer, which buys three things the
scalar threshold cannot show:

- **Depolarization block.** A cell can stop firing as current rises. The search
  reports the first block point as one number (``ThresholdResult.upper_block_uA``);
  the curve shows the shape.
- **Order of recruitment.** Which bystander joins next, and how much headroom is
  really there, read directly off the traces.
- **Where the spike starts.** ``initiation_region`` comes back free from each run —
  soma versus axon initiation as amplitude rises is the axon-avoidance premise made
  visible.

Cost is the same order as one scorecard: the field is solved ONCE per cell and
reused across every amplitude (each is then a matvec), so an N-amplitude sweep over
M cells is N×M NEURON runs and no extra solves.

This lives in ``study`` rather than ``cable`` for the same reason ``SolvedPopulation``
does: it needs ``select_off_targets`` from ``engine.eval``, which already imports
``cable.population``. See ``sweep.SolvedPopulation``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from engine.cable.multisite import run_multisite
from engine.eval import OffTargetSet
from engine.field import AnalyticalBackend, FieldBackend

from .sweep import SolvedPopulation

if TYPE_CHECKING:  # pragma: no cover
    from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig


@dataclass(frozen=True)
class CellActivation:
    """One cell's response across the amplitude grid, aligned index-for-index."""

    cell_id: str
    is_target: bool
    activated: tuple[bool, ...]
    initiation_region: tuple[str | None, ...]

    def crossing_uA(self, amplitudes_uA: Sequence[float]) -> float | None:
        """The first grid amplitude at which this cell fires.

        **Grid resolution, not a threshold.** The bisection in
        ``engine.cable.threshold`` converges to a relative tolerance and is the
        accurate number; this is only as fine as the grid. Kept deliberately
        distinct so the two are never confused for one another.
        """
        for amp, on in zip(amplitudes_uA, self.activated, strict=True):
            if on:
                return amp
        return None

    def blocks(self) -> bool:
        """Whether the cell stops firing again at higher current — depolarization
        block. True only if activation goes on and then off across the grid."""
        seen_on = False
        for on in self.activated:
            if on:
                seen_on = True
            elif seen_on:
                return True
        return False


@dataclass(frozen=True)
class AmplitudeSweep:
    amplitudes_uA: tuple[float, ...]
    cells: tuple[CellActivation, ...]


def amplitude_grid(lo: float, hi: float, n: int, *, spacing: str = "linear") -> tuple[float, ...]:
    """`n` amplitudes from `lo` to `hi`. Log spacing resolves the low end, where
    thresholds actually sit, without spending points on the flat top."""
    if not (lo > 0.0 and hi > lo):
        raise ValueError("need 0 < lo < hi")
    if n < 2:
        raise ValueError("need at least two amplitudes")
    if spacing == "log":
        a, b = math.log(lo), math.log(hi)
        return tuple(math.exp(a + (b - a) * i / (n - 1)) for i in range(n))
    return tuple(lo + (hi - lo) * i / (n - 1) for i in range(n))


def amplitude_sweep(
    patch: RetinalPatch,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    amplitudes_uA: Sequence[float],
    off_target_set: OffTargetSet | None = None,
    backend: FieldBackend | None = None,
    overlap_eps_um: float = 1.0,
    on_amplitude: Callable[[int, float], None] | None = None,
) -> AmplitudeSweep:
    """Drive the whole population at each amplitude in turn.

    Unlike a threshold search this is not adaptive, so it is interruptible and
    reports honest progress: `on_amplitude(i, amp)` fires as each column completes.
    """
    if not amplitudes_uA:
        raise ValueError("an amplitude sweep needs at least one amplitude")
    backend = backend or AnalyticalBackend()
    pop = SolvedPopulation(
        patch,
        array,
        conductivity,
        off_target_set or OffTargetSet(),
        backend,
        overlap_eps_um=overlap_eps_um,
    )

    cells = pop.cells()
    activated: dict[str, list[bool]] = {cid: [] for cid, *_ in cells}
    regions: dict[str, list[str | None]] = {cid: [] for cid, *_ in cells}

    for i, amp in enumerate(amplitudes_uA):
        scaled = replace(config, waveform=replace(config.waveform, amplitude_scale_uA=amp))
        for cid, _is_target, model, solved, severed in cells:
            r = run_multisite(
                model,
                array,
                scaled,
                conductivity,
                solved=solved,
                deactivated=severed,
            )
            activated[cid].append(r.activated)
            regions[cid].append(r.initiation_region)
        if on_amplitude is not None:
            on_amplitude(i, amp)

    return AmplitudeSweep(
        amplitudes_uA=tuple(amplitudes_uA),
        cells=tuple(
            CellActivation(
                cell_id=cid,
                is_target=is_target,
                activated=tuple(activated[cid]),
                initiation_region=tuple(regions[cid]),
            )
            for cid, is_target, *_ in cells
        ),
    )
