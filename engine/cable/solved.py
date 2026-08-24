"""A solved field: the transfer matrix over one placed cell, reusable across configs.

The expensive step in driving a cell is the field solve: building the transfer
matrix ``A`` (mV/µA) from the electrode array to the cell's segment centers. ``A``
is fixed for a given (placed cell, array, conductivity, backend); only the current
vector changes when the configuration (weights, amplitude) changes. A configuration
sweep on a fixed array should therefore solve ``A`` once and reuse it, turning each
subsequent Ve into a cheap matrix-vector product; so should a single threshold
search, which only sweeps amplitude. This is the geometry/configuration split
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
    ``A @ I``: no field solve, just a weighted sum of already-solved columns.
    """

    a: np.ndarray  # (n_segments, n_electrodes), mV/µA
    segs: list  # segment refs aligned with a's rows (same order as segment_coords)
    array: ElectrodeArray  # fixes the electrode/column order for current_vector

    def ve(self, config: StimConfig) -> np.ndarray:
        """Ve (mV) at every segment for this configuration: a weighted sum of ``A``."""
        return self.a @ current_vector(self.array, config)


def solve_field(
    model: RGCModel,
    array: ElectrodeArray,
    conductivity: ConductivityModel,
    backend: FieldBackend | None = None,
    *,
    deactivated: frozenset[int] = frozenset(),
) -> SolvedField:
    """Solve the transfer matrix once for a placed cell under an array + medium.

    ``deactivated`` are segment indices (in ``segment_coords`` order) that the
    ``displace`` overlap policy has severed because they lie inside an electrode
    body. The field is **not** queried there (that point is inside the metal, cut out
    of the FEM mesh, and would raise), and their rows in ``A`` are left zero, so
    ``Ve`` is zero at those segments and the surviving segments key and solve
    unchanged.
    """
    backend = backend or AnalyticalBackend()
    coords, segs = segment_coords(model)
    if not deactivated:
        a = backend.transfer_matrix(array, conductivity, coords)
        return SolvedField(a=a, segs=segs, array=array)
    keep = [i for i in range(len(segs)) if i not in deactivated]
    a = np.zeros((len(segs), len(array.electrodes)), dtype=float)
    if keep:  # all-severed cell -> all-zero A (no drive, never fires)
        a[keep] = backend.transfer_matrix(array, conductivity, coords[keep])
    return SolvedField(a=a, segs=segs, array=array)
