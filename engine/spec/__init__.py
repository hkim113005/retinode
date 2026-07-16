"""Domain model: the five serializable spec objects that describe a simulation.

These are the single source of truth the whole system passes around. The
geometry/configuration split is enforced *structurally*: geometry objects
(ElectrodeArray) carry no current, and configuration objects (StimConfig) carry
no position — so the two cannot blur even under a careless edit.
"""

from .body import CadBody, Cylinder, ElectrodeBody, Frustum, Hemisphere
from .conductivity import (
    ConductivityModel,
    HomogeneousConductivity,
    Layer,
    LayeredConductivity,
)
from .conventions import SCHEMA_VERSION
from .geometry import ArrayPlacement, Electrode, ElectrodeArray, Shape
from .hashing import combine, spec_hash
from .patch import RGC, RetinalPatch
from .serialization import from_json, to_json
from .stim import StimConfig, Waveform
from .study import StudyDefinition, Sweep, Tier
from .validation import Problem, Severity, has_errors, validate, validate_scene

__all__ = [
    "SCHEMA_VERSION",
    # geometry
    "Electrode",
    "ElectrodeArray",
    "ArrayPlacement",
    "ElectrodeBody",
    "Hemisphere",
    "Cylinder",
    "Frustum",
    "CadBody",
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
    # validation
    "Problem",
    "Severity",
    "validate",
    "validate_scene",
    "has_errors",
    # serialization
    "to_json",
    "from_json",
    # hashing
    "spec_hash",
    "combine",
]
