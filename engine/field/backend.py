"""The field backend contract: the transfer matrix is the only handoff.

A backend maps (array, conductivity, query points) to A, the transfer matrix,
where ``A[i, j]`` is the extracellular potential at query point i per unit
current on electrode j. Units are FIXED: A is in mV/uA, so ``Ve[mV] = A @ I[uA]``
with no stray factor (see spec/conventions.py). Linearity of the quasi-static
Laplace problem is what makes one unit-current column per electrode sufficient;
any configuration is then a weighted sum.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

from engine.spec import ConductivityModel, ElectrodeArray, StimConfig


class UnsupportedByBackend(Exception):
    """Raised when a backend is asked to solve outside its regime (e.g. the
    analytical backend with a layered or anisotropic conductivity)."""


class FieldBackend(Protocol):
    """Structural contract every field solver satisfies."""

    name: str

    def transfer_matrix(
        self,
        array: ElectrodeArray,
        conductivity: ConductivityModel,
        query_points_um: np.ndarray,
    ) -> np.ndarray: ...


def backend_solve_params(
    backend: FieldBackend, array: ElectrodeArray, conductivity: ConductivityModel
) -> str | None:
    """The backend's mesh/degree settings that change ``A`` beyond array + conductivity,
    for threading into ``field_key``/``result_key``. ``None`` for backends with no such
    settings (the analytical point source), which keeps their keys unchanged. Only the
    FEM backend implements ``solve_params``; the protocol does not require it."""
    fn = getattr(backend, "solve_params", None)
    return fn(array, conductivity) if callable(fn) else None


def current_vector(array: ElectrodeArray, config: StimConfig) -> np.ndarray:
    """Per-electrode current (uA) aligned to the array's electrode order:
    ``weight * amplitude_scale``, and 0 for electrodes the config does not drive."""
    weights = config.weight_map()
    amp = config.waveform.amplitude_scale_uA
    return np.array([weights.get(e.id, 0.0) * amp for e in array.electrodes], dtype=float)


def potential_mV(a: np.ndarray, currents_uA: np.ndarray) -> np.ndarray:
    """Ve = A @ I: extracellular potential (mV) at each query point."""
    return a @ np.asarray(currents_uA, dtype=float)
