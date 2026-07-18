"""Field engine: backends that produce the transfer matrix A (mV/uA).

The transfer matrix is the universal handoff between field solvers and the cable
engine — the cable engine never sees a solver, only Ve sampled at its
compartments. See backend.py for the contract.
"""

from .analytical import AnalyticalBackend
from .backend import (
    FieldBackend,
    UnsupportedByBackend,
    backend_solve_params,
    current_vector,
    potential_mV,
)
from .fem_fenicsx import FenicsxBackend
from .fem_ngsolve import NGSolveBackend

__all__ = [
    "FieldBackend",
    "UnsupportedByBackend",
    "AnalyticalBackend",
    "FenicsxBackend",
    "NGSolveBackend",
    "backend_solve_params",
    "current_vector",
    "potential_mV",
]
