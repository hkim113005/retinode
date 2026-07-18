"""View payloads: the small, explicit data contract (§16).

Pure data — a field grid, a scorecard dict, the validation report — computed
straight from the engine. Fast (analytical field only, no NEURON) and fully
testable.

These outlived the Dash app they were written for (retired in P7 S8). They stay
because they are the **independent oracle** for the API: ``tests/api/test_compare``
asserts that ``/compare`` returns the same numbers this computes, by a separate
route. Deleting them would leave the API checked only against a snapshot of
itself. Keep them engine-only and plotly-free — ``api.service`` reads
``validation_report.json`` by path rather than importing this module, precisely so
nothing heavy leaks into the API process.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from engine.field import AnalyticalBackend, FieldBackend, current_vector
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .scene import cell_depth_um

_VALIDATION_REPORT = Path(__file__).parent / "validation_report.json"


def load_validation_report() -> dict[str, Any]:
    """The committed validation report the app renders (empty shell if absent)."""
    if not _VALIDATION_REPORT.exists():
        return {"n_pass": 0, "n_total": 0, "reproductions": []}
    return json.loads(_VALIDATION_REPORT.read_text())



@dataclass(frozen=True)
class FieldGrid:
    xs: np.ndarray  # µm, length n
    ys: np.ndarray  # µm, length n
    ve_mV: np.ndarray  # (n, n) extracellular potential at the cell plane


def field_grid(
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    extent_um: float = 160.0,
    n: int = 61,
    z_um: float | None = None,
    backend: FieldBackend | None = None,
) -> FieldGrid:
    """Ve (mV) on a square grid at the cell plane — the analytical field preview."""
    backend = backend or AnalyticalBackend()
    z = cell_depth_um() if z_um is None else z_um
    xs = np.linspace(-extent_um, extent_um, n)
    ys = np.linspace(-extent_um, extent_um, n)
    xx, yy = np.meshgrid(xs, ys)
    points = np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, z)])
    ve = backend.transfer_matrix(array, conductivity, points) @ current_vector(array, config)
    return FieldGrid(xs=xs, ys=ys, ve_mV=ve.reshape(n, n))


def scorecard_data(result: Any) -> dict[str, Any]:
    """Flat display values for the result scorecard (pure — no formatting)."""
    if not result.activated or result.window is None or result.sow is None:
        return {"activated": False}
    w, sow = result.window, result.sow
    return {
        "activated": True,
        "target_uA": w.target_uA,
        "off_min_uA": sow.off_min_uA,
        "ratio": sow.ratio,
        "window_lo_uA": w.target_uA,
        "window_hi_uA": w.window_hi_uA,
        "usable_margin_uA": w.usable_margin_uA,
        "usable": w.is_usable,
        "limiting": w.limiting,
        "safety_ceiling_uA": w.safety_ceiling_uA,
        "safe_at_target": bool(result.safety_at_target and result.safety_at_target.safe),
    }
