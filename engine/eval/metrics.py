"""Selectivity metrics: the selective operating window, computed from thresholds.

Pure arithmetic over already-computed thresholds (the thresholds themselves come
from the cable engine later), so this is testable now with synthetic values.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SOW:
    """The selective operating window.

    ``margin_uA = off_min_uA - target_uA`` is positive when a range of amplitudes
    fires only the target; ``ratio = off_min_uA / target_uA`` makes it comparable
    across cells of different absolute sensitivity. With no off-targets the window
    is genuinely unbounded (margin/ratio = inf).

    ``off_min_is_lower_bound`` marks the different case that used to be reported
    identically: off-target cells exist, but one or more never fired within the
    searched amplitude range, so the true ``off_min_uA`` is somewhere *above* the
    search cap and is not known. Then ``off_min_uA`` is the cap — a lower bound, not
    a measurement — and everything derived from it (margin, ratio, and the window
    the evaluator builds) is a lower bound too. Reporting inf here claimed
    selectivity out to the safety ceiling over amplitudes that were never probed.
    """

    target_uA: float
    off_min_uA: float
    margin_uA: float
    ratio: float
    limiting_off_id: str | None
    off_min_is_lower_bound: bool = False
    unreached_off_ids: tuple[str, ...] = ()


def selective_operating_window(
    target_threshold_uA: float,
    off_target_thresholds_uA: dict[str, float],
    *,
    unreached_off_ids: tuple[str, ...] = (),
    searched_max_uA: float | None = None,
) -> SOW:
    """The selective window from measured thresholds.

    ``unreached_off_ids`` are off-target cells that were selected and searched but
    never fired below ``searched_max_uA``. They are NOT absent bystanders: their
    thresholds exist and are above the cap. Passing them keeps the window bounded by
    what was actually probed instead of extending it to infinity over unchecked
    amplitudes.
    """
    if target_threshold_uA <= 0.0:
        raise ValueError("target threshold must be positive")

    if not off_target_thresholds_uA:
        if unreached_off_ids and searched_max_uA is not None:
            # Bystanders exist; the search just never reached them. The honest bound
            # is the cap, flagged as a lower bound — not inf.
            cap = float(searched_max_uA)
            return SOW(
                target_uA=target_threshold_uA,
                off_min_uA=cap,
                margin_uA=cap - target_threshold_uA,
                ratio=cap / target_threshold_uA,
                limiting_off_id=None,
                off_min_is_lower_bound=True,
                unreached_off_ids=tuple(unreached_off_ids),
            )
        return SOW(
            target_uA=target_threshold_uA,
            off_min_uA=math.inf,
            margin_uA=math.inf,
            ratio=math.inf,
            limiting_off_id=None,
        )

    limiting_off_id = min(off_target_thresholds_uA, key=lambda k: off_target_thresholds_uA[k])
    off_min = off_target_thresholds_uA[limiting_off_id]
    return SOW(
        target_uA=target_threshold_uA,
        off_min_uA=off_min,
        margin_uA=off_min - target_threshold_uA,
        ratio=off_min / target_threshold_uA,
        limiting_off_id=limiting_off_id,
        # A measured minimum below the cap is exact even if OTHER bystanders were
        # truncated: they can only be higher, so they cannot lower this bound.
        off_min_is_lower_bound=False,
        unreached_off_ids=tuple(unreached_off_ids),
    )
