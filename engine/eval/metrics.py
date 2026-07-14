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
    is unbounded (margin/ratio = inf).
    """

    target_uA: float
    off_min_uA: float
    margin_uA: float
    ratio: float
    limiting_off_id: str | None


def selective_operating_window(
    target_threshold_uA: float,
    off_target_thresholds_uA: dict[str, float],
) -> SOW:
    if target_threshold_uA <= 0.0:
        raise ValueError("target threshold must be positive")

    if not off_target_thresholds_uA:
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
    )
