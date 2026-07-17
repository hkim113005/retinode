"""Engine → typed payloads. Pure functions the routes call.

The field grid mirrors ``app.views.field_grid`` exactly (same backend, same z
plane) so the API and the Dash view can never disagree — locked by a parity test.
Deliberately imports only the engine and the pure ``app.scene`` depth convention;
no plotly/dash, so the API server stays light and NEURON-free on the field path.
"""

from __future__ import annotations

import numpy as np

from app.scene import cell_depth_um
from engine.field import AnalyticalBackend, FieldBackend, current_vector
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .models import FieldGridResponse, ScorecardResponse


def field_grid_payload(
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    extent_um: float,
    n: int,
    backend: FieldBackend | None = None,
) -> FieldGridResponse:
    """Ve (mV) on an ``n × n`` grid at the cell plane — the analytical preview."""
    backend = backend or AnalyticalBackend()
    z = cell_depth_um()
    xs = np.linspace(-extent_um, extent_um, n)
    ys = np.linspace(-extent_um, extent_um, n)
    xx, yy = np.meshgrid(xs, ys)
    points = np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, z)])
    ve = backend.transfer_matrix(array, conductivity, points) @ current_vector(array, config)
    ve = ve.reshape(n, n)
    return FieldGridResponse(
        xs_um=xs.tolist(),
        ys_um=ys.tolist(),
        ve_mV=ve.tolist(),
        vmax_mV=float(np.abs(ve).max()) or 1.0,
    )


def scorecard_payload(result) -> ScorecardResponse:  # noqa: ANN001 - an EvaluationResult
    """Map an evaluation result to the scorecard payload (mirrors
    ``app.views.scorecard_data``)."""
    if not result.activated or result.window is None or result.sow is None:
        return ScorecardResponse(activated=False)
    w, sow = result.window, result.sow
    return ScorecardResponse(
        activated=True,
        target_uA=w.target_uA,
        off_min_uA=sow.off_min_uA,
        ratio=sow.ratio,
        window_lo_uA=w.target_uA,
        window_hi_uA=w.window_hi_uA,
        usable_margin_uA=w.usable_margin_uA,
        usable=w.is_usable,
        limiting=w.limiting,
        safety_ceiling_uA=w.safety_ceiling_uA,
        safe_at_target=bool(result.safety_at_target and result.safety_at_target.safe),
    )
