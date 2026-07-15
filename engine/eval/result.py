"""The scored evaluation result: the Gate-1 deliverable, self-describing.

An :class:`EvaluationResult` carries the operating window (safe *and* selective),
the underlying SOW and thresholds, the per-electrode safety at the operating
amplitude, and the provenance hashes that key it. Everything needed to interpret
or reproduce the score travels with it — nothing is implicit in the caller.
"""

from __future__ import annotations

from dataclasses import dataclass

from engine.cable.population import PopulationThresholds

from .metrics import SOW
from .safety import SafetyReport


@dataclass(frozen=True)
class OperatingWindow:
    """The amplitude band that fires only the target *and* stays within charge limits.

    ``[target_uA, window_hi_uA)`` where ``window_hi_uA = min(selective_hi_uA,
    safety_ceiling_uA)``. ``limiting`` names what caps it: an off-target's
    threshold, the safety ceiling, or neither (unbounded). The window is usable
    only when ``usable_margin_uA > 0`` — the target fires below whatever binds.
    """

    target_uA: float
    selective_hi_uA: float  # lowest off-target threshold (top of selective-only band)
    safety_ceiling_uA: float  # max safe amplitude_scale
    window_hi_uA: float  # min(selective_hi, safety_ceiling)
    usable_margin_uA: float  # window_hi - target (may be <= 0)
    limiting: str  # "off_target" | "safety" | "none"

    @property
    def is_usable(self) -> bool:
        return self.usable_margin_uA > 0.0


@dataclass(frozen=True)
class EvaluationResult:
    """A configuration's score plus the provenance that identifies it."""

    result_key: str
    evaluator_version: str
    field_key: str
    # provenance: content hashes of the scored inputs
    config_hash: str
    patch_hash: str
    offtarget_hash: str
    # the score
    thresholds: PopulationThresholds
    activated: bool  # did the target fire within the searched amplitude range?
    sow: SOW | None  # selective window (None if the target never fired)
    window: OperatingWindow | None  # safe-and-selective window (None if not activated)
    safety_at_target: SafetyReport | None  # per-electrode safety at the target threshold

    def same_offtarget(self, other: EvaluationResult) -> bool:
        return self.offtarget_hash == other.offtarget_hash


def require_same_offtarget(a: EvaluationResult, b: EvaluationResult) -> None:
    """Refuse to compare two results scored against different off-target sets.

    The SOW is only comparable across configs when both were measured against the
    same off-target definition; comparing across differing sets is a category
    error the evaluator will not let pass silently.
    """
    if a.offtarget_hash != b.offtarget_hash:
        raise ValueError(
            "cannot compare evaluations scored against different off-target sets "
            f"({a.offtarget_hash[:12]} != {b.offtarget_hash[:12]})"
        )
