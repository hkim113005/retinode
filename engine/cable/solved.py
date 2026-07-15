"""A solved field: the transfer matrix over one placed cell, reusable across configs.

The expensive step in driving a cell is the field solve — building the transfer
matrix ``A`` (mV/µA) from the electrode array to the cell's segment centers. ``A``
is fixed for a given (placed cell, array, conductivity, backend); only the current
vector changes when the configuration (weights, amplitude) changes. So a
configuration sweep on a fixed array — and even a single threshold search, which
sweeps amplitude — should solve ``A`` once and reuse it, turning each subsequent
Ve into a cheap matrix-vector product. This is the geometry/configuration split
(project plan §6, §9) made concrete: touch geometry and ``A`` is rebuilt; touch
only the configuration and ``A`` is reused.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.field import AnalyticalBackend, FieldBackend, current_vector
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .drive import segment_coords
from .morphology import RGCModel


@dataclass(frozen=True)
class SolvedField:
    """Transfer matrix ``A`` over a placed cell's segments, plus the aligned segments.

    ``a[i, j]`` is Ve (mV) at segment ``i`` per unit current (µA) on electrode
    ``j``, in the array's electrode order. ``ve(config)`` is the cheap reuse
    ``A @ I`` — no field solve, just a weighted sum of already-solved columns.
    """

    a: np.ndarray  # (n_segments, n_electrodes), mV/µA
    segs: list  # segment refs aligned with a's rows (same order as segment_coords)
    array: ElectrodeArray  # fixes the electrode/column order for current_vector

    def ve(self, config: StimConfig) -> np.ndarray:
        """Ve (mV) at every segment for this configuration — a weighted sum of ``A``."""
        return self.a @ current_vector(self.array, config)


def solve_field(
    model: RGCModel,
    array: ElectrodeArray,
    conductivity: ConductivityModel,
    backend: FieldBackend | None = None,
) -> SolvedField:
    """Solve the transfer matrix once for a placed cell under an array + medium."""
    backend = backend or AnalyticalBackend()
    coords, segs = segment_coords(model)
    a = backend.transfer_matrix(array, conductivity, coords)
    return SolvedField(a=a, segs=segs, array=array)
