"""Activation-threshold search that is aware of non-monotonicity (not naive bisection).

Extracellular stimulation is non-monotonic: a cell fires above a lower threshold
but can fall silent again at high amplitude (depolarization block / upper
threshold). Naive bisection can converge to a spurious value, so the search
(1) climbs a geometric ladder to *bracket* the lowest activating amplitude,
(2) bisects within that bracket to tolerance, then (3) scans above to check that
activation persists, recording any upper block.

`find_threshold` is generic (takes an `activates(amp) -> bool` predicate), so the
algorithm is tested on synthetic activation curves with no NEURON.
`extracellular_threshold` wraps it around a real field-driven cell.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ThresholdResult:
    threshold_uA: float | None  # lowest activating amplitude (None if never fires)
    bracket_uA: tuple[float, float] | None  # (last inactive, first active) before bisection
    tolerance_uA: float
    activates_above: bool  # activation persists from threshold up to amp_max
    upper_block_uA: float | None  # first amplitude above threshold that stops firing


def find_threshold(
    activates: Callable[[float], bool],
    *,
    amp_min: float = 0.1,
    amp_max: float = 1000.0,
    ladder: float = 1.4,
    rel_tol: float = 0.02,
) -> ThresholdResult:
    # 1. climb a geometric ladder to bracket the first activating amplitude.
    #
    # The last rung is CLAMPED to amp_max, the same clamp step 3 below already uses.
    # Climbing by bare multiplication instead left the band between the top rung and
    # amp_max unprobed (at ladder=1.5 that is the top 33% of the declared range: with
    # amp_min=2, amp_max=500 the highest amplitude ever tested was 389.2 µA). A cell
    # whose threshold fell in that band returned None. Every caller reads that as
    # "never fires" rather than "not looked for", so such a cell dropped out of the
    # off-target set entirely, taking the selective-window bound with it.
    last_inactive: float | None = None
    first_active: float | None = None
    a = amp_min
    at_max = False
    while a <= amp_max * (1.0 + 1e-9):
        if a >= amp_max * (1.0 - 1e-9):
            a, at_max = amp_max, True
        if activates(a):
            first_active = a
            break
        last_inactive = a
        if at_max:
            break
        a = min(a * ladder, amp_max)
    if first_active is None:
        return ThresholdResult(None, None, 0.0, False, None)

    # 2. bisect within the bracket to tolerance.
    bracket = (last_inactive if last_inactive is not None else 0.0, first_active)
    lo, hi = bracket
    tol = rel_tol * first_active
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if activates(mid):
            hi = mid
        else:
            lo = mid
    threshold = hi

    # 3. scan above the threshold for an upper block (non-monotonicity).
    activates_above = True
    upper_block: float | None = None
    a = threshold
    while a < amp_max:
        a = min(a * ladder, amp_max)
        if not activates(a):
            activates_above = False
            upper_block = a
            break

    return ThresholdResult(threshold, bracket, tol, activates_above, upper_block)


def extracellular_threshold(
    model,
    array,
    config,
    conductivity,
    *,
    backend=None,
    monophasic: bool = True,
    amp_min: float = 1.0,
    amp_max: float = 500.0,
    ladder: float = 1.5,
    rel_tol: float = 0.03,
) -> ThresholdResult:
    """Threshold (µA amplitude) for a field-driven cell, scaling the config's amplitude.

    Uses the monophasic excitatory phase by default so the threshold is clean
    (a biphasic pulse's reversed phase can itself excite; see drive.py).
    """
    from .drive import run_extracellular_pulse

    def activates(amp: float) -> bool:
        wf = dataclasses.replace(config.waveform, amplitude_scale_uA=amp)
        scaled = dataclasses.replace(config, waveform=wf)
        result = run_extracellular_pulse(
            model, array, scaled, conductivity, backend=backend, monophasic=monophasic
        )
        return result.n_spikes >= 1

    return find_threshold(
        activates, amp_min=amp_min, amp_max=amp_max, ladder=ladder, rel_tol=rel_tol
    )
