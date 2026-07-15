"""Validation: property tests, cross-backend checks, and literature reproductions.

S5 provides the single-cell threshold reproductions; each returns a Reproduction
recording what was measured and whether it holds.
"""

from .reproduction import Reproduction
from .single_cell import (
    all_reproductions,
    axon_of_passage_is_excitable,
    spike_initiates_at_sodium_band,
    strength_duration_decreases,
    threshold_rises_with_distance,
    thresholds_in_physiological_range,
)

__all__ = [
    "Reproduction",
    "all_reproductions",
    "threshold_rises_with_distance",
    "axon_of_passage_is_excitable",
    "spike_initiates_at_sodium_band",
    "strength_duration_decreases",
    "thresholds_in_physiological_range",
]
