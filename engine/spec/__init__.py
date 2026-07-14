"""Domain model: the five serializable spec objects that describe a simulation.

These are the single source of truth the whole system passes around. The
geometry/configuration split is enforced *structurally*: geometry objects
(ElectrodeArray) carry no current, and configuration objects (StimConfig) carry
no position — so the two cannot blur even under a careless edit.
"""

from .conductivity import (
    ConductivityModel,
    HomogeneousConductivity,
    Layer,
    LayeredConductivity,
)
from .conventions import SCHEMA_VERSION
from .geometry import Electrode, ElectrodeArray, Shape
from .patch import RGC, RetinalPatch
from .stim import StimConfig, Waveform
from .study import StudyDefinition, Sweep, Tier

__all__ = [
    "SCHEMA_VERSION",
    # geometry
    "Electrode",
    "ElectrodeArray",
    "Shape",
    # configuration
    "Waveform",
    "StimConfig",
    # conductivity
    "Layer",
    "HomogeneousConductivity",
    "LayeredConductivity",
    "ConductivityModel",
    # patch
    "RGC",
    "RetinalPatch",
    # study
    "Sweep",
    "StudyDefinition",
    "Tier",
]
