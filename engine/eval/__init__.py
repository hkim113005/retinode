"""The evaluator: one fixed scorer, called identically for every configuration.

S1 provides the pure arithmetic — charge/safety, the off-target set, and the
selective operating window. The threshold-driven pieces (evaluator, result) are
wired in once the cable engine lands.
"""

from .evaluator import EVALUATOR_VERSION, evaluate
from .metrics import SOW, selective_operating_window
from .offtarget import OffTargetSet, select_off_targets
from .overlap import (
    CompartmentFlag,
    OverlapConflict,
    OverlapReport,
    check_overlap,
    resolve_overlap,
)
from .result import EvaluationResult, OperatingWindow, require_same_offtarget
from .safety import (
    ElectrodeSafety,
    SafetyLimits,
    SafetyReport,
    assess_safety,
    charge_per_phase_uC,
    electrode_area_um2,
    max_safe_amplitude_uA,
)

__all__ = [
    # safety
    "SafetyLimits",
    "ElectrodeSafety",
    "SafetyReport",
    "assess_safety",
    "charge_per_phase_uC",
    "electrode_area_um2",
    "max_safe_amplitude_uA",
    # off-target set
    "OffTargetSet",
    "select_off_targets",
    # cell/electrode overlap (P6 S4)
    "check_overlap",
    "resolve_overlap",
    "OverlapReport",
    "CompartmentFlag",
    "OverlapConflict",
    # metrics
    "SOW",
    "selective_operating_window",
    # evaluator + result
    "evaluate",
    "EVALUATOR_VERSION",
    "EvaluationResult",
    "OperatingWindow",
    "require_same_offtarget",
]
