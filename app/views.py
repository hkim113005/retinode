"""View payloads and figures: the small, explicit data contract (§16).

Two halves: pure *data* (a field grid, a scorecard dict) computed straight from
the engine, and the Plotly *figure* built from that data. The data functions are
fast (analytical field only, no NEURON) and fully testable; the figure is a thin
rendering of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import plotly.graph_objects as go

from engine.field import AnalyticalBackend, FieldBackend, current_vector
from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig

from .scene import cell_depth_um

# A restrained palette shared by the figures (matches the CSS).
_INK = "#1f2933"
_MUTED = "#8a94a6"
_ACCENT = "#2f6f6a"
_GRID_BG = "rgba(0,0,0,0)"


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


def field_figure(
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    patch: RetinalPatch,
    *,
    extent_um: float = 130.0,
) -> go.Figure:
    """A clean heatmap of Ve with electrode outlines and cell markers overlaid."""
    grid = field_grid(array, config, conductivity, extent_um=extent_um)
    vmax = float(np.abs(grid.ve_mV).max()) or 1.0

    fig = go.Figure(
        go.Heatmap(
            x=grid.xs,
            y=grid.ys,
            z=grid.ve_mV,
            zmid=0.0,
            zmin=-vmax,
            zmax=vmax,
            colorscale="RdBu",
            colorbar=dict(
                title=dict(text="Ve (mV)", side="right", font=dict(size=11, color=_MUTED)),
                thickness=10,
                outlinewidth=0,
                tickfont=dict(size=10, color=_MUTED),
                len=0.9,
            ),
            hovertemplate="x %{x:.0f} µm<br>y %{y:.0f} µm<br>Ve %{z:.2f} mV<extra></extra>",
        )
    )

    # electrode outlines
    for e in array.electrodes:
        r = e.size_um / 2.0
        fig.add_shape(
            type="circle",
            x0=e.pos_um[0] - r,
            x1=e.pos_um[0] + r,
            y0=e.pos_um[1] - r,
            y1=e.pos_um[1] + r,
            line=dict(color=_INK, width=1.5),
            fillcolor="rgba(255,255,255,0.35)",
        )

    # cell markers: target filled, off-targets hollow
    tx = [c.soma_um[0] for c in patch.cells if c.id == patch.target_id]
    ty = [c.soma_um[1] for c in patch.cells if c.id == patch.target_id]
    ox = [c.soma_um[0] for c in patch.cells if c.id != patch.target_id]
    oy = [c.soma_um[1] for c in patch.cells if c.id != patch.target_id]
    fig.add_trace(
        go.Scatter(
            x=ox,
            y=oy,
            mode="markers",
            name="off-target",
            marker=dict(size=11, color="rgba(0,0,0,0)", line=dict(color=_INK, width=1.5)),
            hovertemplate="off-target<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            x=tx,
            y=ty,
            mode="markers",
            name="target",
            marker=dict(size=12, color=_ACCENT, line=dict(color="white", width=1.5)),
            hovertemplate="target<extra></extra>",
        )
    )

    fig.update_layout(
        margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=_GRID_BG,
        plot_bgcolor=_GRID_BG,
        showlegend=False,
        font=dict(family="system-ui, -apple-system, sans-serif", color=_MUTED),
        xaxis=dict(
            scaleanchor="y",
            constrain="domain",
            zeroline=False,
            showgrid=False,
            ticks="",
            title=dict(text="µm", font=dict(size=11)),
        ),
        yaxis=dict(zeroline=False, showgrid=False, ticks="", constrain="domain"),
        height=400,
        autosize=True,
    )
    return fig


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
