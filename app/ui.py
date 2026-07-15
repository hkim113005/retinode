"""The Dash layout, callbacks, and app factory.

One page: a control rail on the left, a live analytical field preview and a
result scorecard on the right. Designing the array/stimulus/patch updates the
field instantly (no NEURON); "Evaluate selectivity" runs the real pipeline and
fills the scorecard.
"""

from __future__ import annotations

import math
from typing import Any

from dash import Dash, Input, Output, State, dcc, html

from engine.eval import evaluate

from .scene import build_scene
from .views import field_figure, scorecard_data

_LAYOUTS = [
    {"label": "Single disk", "value": "single"},
    {"label": "Bipolar pair", "value": "bipolar"},
]


def _fmt_uA(x: float) -> str:
    return "∞" if math.isinf(x) else f"{x:.1f}"


def _control(cid: str, title: str, lo: float, hi: float, value: float, step: float) -> html.Div:
    return html.Div(
        className="control",
        children=[
            html.Div(
                className="control-head",
                children=[
                    html.Span(title, className="control-name"),
                    html.Span(id=f"{cid}-val", className="control-val"),
                ],
            ),
            dcc.Slider(
                id=cid, min=lo, max=hi, step=step, value=value, marks=None, updatemode="drag"
            ),
        ],
    )


def _section(title: str, *children: Any) -> html.Div:
    return html.Div(
        className="section", children=[html.Div(title, className="section-title"), *children]
    )


def _control_rail() -> html.Aside:
    return html.Aside(
        className="rail",
        children=[
            _section(
                "Array",
                dcc.RadioItems(id="layout", options=_LAYOUTS, value="single", className="radio"),
                _control("electrode-um", "Electrode diameter", 5, 40, 10, 1),
                html.Div(
                    id="pitch-row",
                    children=[_control("pitch-um", "Pair pitch", 20, 160, 60, 5)],
                ),
            ),
            _section("Stimulus", _control("phase-width", "Phase width", 50, 500, 200, 10)),
            _section("Patch", _control("neighbor-um", "Neighbour distance", 20, 160, 40, 5)),
            _section("Tissue", _control("sigma", "Conductivity", 0.2, 2.0, 1.0, 0.1)),
            html.Button("Evaluate selectivity", id="evaluate-btn", className="run-btn", n_clicks=0),
        ],
    )


def _stat(value: str, label: str, sub: str | None = None, cls: str = "stat") -> html.Div:
    children = [html.Div(value, className="stat-value"), html.Div(label, className="stat-label")]
    if sub:
        children.append(html.Div(sub, className="stat-sub"))
    return html.Div(className=cls, children=children)


def _scorecard(data: dict[str, Any]) -> Any:
    if not data.get("activated"):
        return html.Div(
            "The target did not fire within the searched amplitude range.",
            className="scorecard-empty",
        )
    limit = {"off_target": "off-target", "safety": "safety", "none": "unbounded"}[data["limiting"]]
    usable = data["usable"]
    return html.Div(
        className="scorecard",
        children=[
            html.Div(
                "usable window" if usable else "no usable window",
                className=f"badge {'usable' if usable else 'blocked'}",
            ),
            _stat(
                f"{_fmt_uA(data['window_lo_uA'])} – {_fmt_uA(data['window_hi_uA'])} µA",
                "operating window",
                f"limited by {limit}",
                cls="stat stat-hero",
            ),
            html.Div(
                className="stat-row",
                children=[
                    _stat(f"{_fmt_uA(data['target_uA'])} µA", "target threshold"),
                    _stat(
                        "∞×" if math.isinf(data["ratio"]) else f"{data['ratio']:.2f}×",
                        "selectivity",
                    ),
                    _stat(
                        f"{_fmt_uA(data['safety_ceiling_uA'])} µA",
                        "safety",
                        "safe at target" if data["safe_at_target"] else "unsafe",
                    ),
                ],
            ),
        ],
    )


def layout() -> html.Div:
    return html.Div(
        className="app",
        children=[
            html.Header(
                className="topbar",
                children=[
                    html.Div("Retinode", className="wordmark"),
                    html.Div("epiretinal electrode selectivity", className="tagline"),
                ],
            ),
            html.Main(
                className="grid",
                children=[
                    _control_rail(),
                    html.Section(
                        className="stage",
                        children=[
                            html.Div(
                                className="card view-card",
                                children=[
                                    html.Div("Field preview", className="card-title"),
                                    html.Div(
                                        "Extracellular potential at the cell plane — "
                                        "the cathodic well (red) is where cells depolarise.",
                                        className="card-hint",
                                    ),
                                    dcc.Graph(
                                        id="field-graph",
                                        config={"displayModeBar": False, "responsive": True},
                                    ),
                                ],
                            ),
                            html.Div(
                                className="card result-card",
                                children=[
                                    html.Div("Selective operating window", className="card-title"),
                                    dcc.Loading(
                                        html.Div(
                                            html.Div(
                                                "Set up a scene, then evaluate to find the "
                                                "safe-and-selective amplitude window.",
                                                className="scorecard-empty",
                                            ),
                                            id="scorecard-slot",
                                        ),
                                        type="dot",
                                        color="#2f6f6a",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )


def register_callbacks(app: Dash) -> None:
    @app.callback(Output("pitch-row", "style"), Input("layout", "value"))
    def _toggle_pitch(layout_value: str) -> dict[str, str]:
        return {} if layout_value == "bipolar" else {"display": "none"}

    @app.callback(
        Output("electrode-um-val", "children"),
        Output("pitch-um-val", "children"),
        Output("phase-width-val", "children"),
        Output("neighbor-um-val", "children"),
        Output("sigma-val", "children"),
        Input("electrode-um", "value"),
        Input("pitch-um", "value"),
        Input("phase-width", "value"),
        Input("neighbor-um", "value"),
        Input("sigma", "value"),
    )
    def _value_labels(electrode_um, pitch_um, phase_width, neighbor_um, sigma):
        return (
            f"{electrode_um:g} µm",
            f"{pitch_um:g} µm",
            f"{phase_width:g} µs",
            f"{neighbor_um:g} µm",
            f"{sigma:g} S/m",
        )

    @app.callback(
        Output("field-graph", "figure"),
        Input("layout", "value"),
        Input("electrode-um", "value"),
        Input("pitch-um", "value"),
        Input("phase-width", "value"),
        Input("neighbor-um", "value"),
        Input("sigma", "value"),
    )
    def _preview(layout_value, electrode_um, pitch_um, phase_width, neighbor_um, sigma):
        scene = build_scene(
            layout=layout_value,
            electrode_um=electrode_um,
            pitch_um=pitch_um,
            phase_width_us=phase_width,
            neighbor_um=neighbor_um,
            sigma_S_per_m=sigma,
        )
        return field_figure(scene.array, scene.config, scene.conductivity, scene.patch)

    @app.callback(
        Output("scorecard-slot", "children"),
        Input("evaluate-btn", "n_clicks"),
        State("layout", "value"),
        State("electrode-um", "value"),
        State("pitch-um", "value"),
        State("phase-width", "value"),
        State("neighbor-um", "value"),
        State("sigma", "value"),
        prevent_initial_call=True,
    )
    def _evaluate(_clicks, layout_value, electrode_um, pitch_um, phase_width, neighbor_um, sigma):
        scene = build_scene(
            layout=layout_value,
            electrode_um=electrode_um,
            pitch_um=pitch_um,
            phase_width_us=phase_width,
            neighbor_um=neighbor_um,
            sigma_S_per_m=sigma,
        )
        result = evaluate(scene.patch, scene.array, scene.config, scene.conductivity)
        return _scorecard(scorecard_data(result))


def create_app() -> Dash:
    app = Dash(__name__, title="Retinode")
    app.layout = layout()
    register_callbacks(app)
    return app
