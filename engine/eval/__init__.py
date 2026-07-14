"""The evaluator: one fixed scorer, called identically for every configuration.

S1 provides the pure arithmetic — charge/safety, the off-target set, and the
selective operating window. The threshold-driven pieces (evaluator, result) are
wired in once the cable engine lands.
"""

from .metrics import SOW, selective_operating_window
from .offtarget import OffTargetSet, select_off_targets
from .safety import (
    ElectrodeSafety,
    SafetyLimits,
    SafetyReport,
    assess_safety,
    charge_per_phase_uC,
    electrode_area_um2,
)

__all__ = [
    # safety
    "SafetyLimits",
    "ElectrodeSafety",
    "SafetyReport",
    "assess_safety",
    "charge_per_phase_uC",
    "electrode_area_um2",
    # off-target set
    "OffTargetSet",
    "select_off_targets",
    # metrics
    "SOW",
    "selective_operating_window",
]
