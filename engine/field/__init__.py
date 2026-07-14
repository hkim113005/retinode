"""Field engine: backends that produce the transfer matrix A (mV/uA).

The transfer matrix is the universal handoff between field solvers and the cable
engine — the cable engine never sees a solver, only Ve sampled at its
compartments. See backend.py for the contract.
"""

from .analytical import AnalyticalBackend
from .backend import (
    FieldBackend,
    UnsupportedByBackend,
    current_vector,
    potential_mV,
)

__all__ = [
    "FieldBackend",
    "UnsupportedByBackend",
    "AnalyticalBackend",
    "current_vector",
    "potential_mV",
]
