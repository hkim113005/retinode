"""The Dash layout, callbacks, and app factory.

One page: a control rail on the left, a live analytical field preview and a
result scorecard on the right, and a strip of recent runs beneath them for
comparison. Designing the array/stimulus/patch updates the field instantly (no
NEURON); "Evaluate selectivity" runs the real pipeline, fills the scorecard, and
adds the run to the strip. Clicking a past run restores its settings.
"""

from __future__ import annotations

import math
from typing import Any

from dash import ALL, Dash, Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate

from engine.eval import evaluate

from .scene import build_scene
from .views import field_figure, load_validation_report, scorecard_data

_LAYOUTS = [
    {"label": "Single disk", "value": "single"},
    {"label": "Bipolar pair", "value": "bipolar"},
]
_MAX_HISTORY = 6
_ACCENT = "#0a84ff"


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


def _run_card(record: dict[str, Any], index: int, is_latest: bool) -> Any:
    p, s = record["params"], record["score"]
    lay = "Bipolar" if p["layout"] == "bipolar" else "Single"
    if not s.get("activated"):
        window, ratio, verdict = "no activation", "—", "blocked"
    else:
        window = f"{_fmt_uA(s['window_lo_uA'])}–{_fmt_uA(s['window_hi_uA'])} µA"
        ratio = "∞× selectivity" if math.isinf(s["ratio"]) else f"{s['ratio']:.2f}× selectivity"
        verdict = "usable" if s["usable"] else "blocked"
    return html.Button(
        id={"type": "run-card", "index": index},
        n_clicks=0,
        className=f"run-card {'latest' if is_latest else ''}",
        children=[
            html.Div(
                className="run-card-head",
                children=[
                    html.Span(className=f"run-dot {verdict}"),
                    html.Span("latest" if is_latest else f"#{index + 1}", className="run-tag"),
                ],
            ),
            html.Div(window, className="run-window"),
            html.Div(ratio, className="run-ratio"),
            html.Div(f"{lay} · {p['phase_width']:g} µs", className="run-title"),
            html.Div(
                f"nbr {p['neighbor_um']:g} µm · Ø{p['electrode_um']:g} µm",
                className="run-sub",
            ),
        ],
    )


def _runs_strip(history: list[dict[str, Any]] | None) -> Any:
    if not history:
        return html.Div("Evaluated runs line up here to compare.", className="runs-empty")
    return [_run_card(rec, i, i == 0) for i, rec in enumerate(history)]


def _val_row(rep: dict[str, Any]) -> html.Div:
    return html.Div(
        className="val-row",
        children=[
            html.Span(className=f"val-dot {'ok' if rep['passed'] else 'fail'}"),
            html.Div(
                className="val-body",
                children=[
                    html.Div(rep["name"], className="val-name"),
                    html.Div(rep["measured"], className="val-measured"),
                ],
            ),
            html.Div(rep["source"], className="val-source"),
        ],
    )


def _validation_panel() -> html.Div:
    report = load_validation_report()
    reps = report.get("reproductions", [])
    body: Any = (
        [_val_row(r) for r in reps]
        if reps
        else html.Div(
            "Generate the report with `python -m engine.validate.report`.",
            className="runs-empty",
        )
    )
    return html.Div(
        className="card val-card",
        children=[
            html.Div(
                className="val-head",
                children=[
                    html.Div("Validation", className="card-title"),
                    html.Div(
                        f"{report.get('n_pass', 0)} / {report.get('n_total', 0)} reproduce",
                        className="val-count",
                    ),
                ],
            ),
            html.Div(
                "Published results this model recovers — gated in CI.", className="card-hint"
            ),
            html.Div(body, className="val-list"),
        ],
    )


def layout() -> html.Div:
    return html.Div(
        className="app",
        children=[
            dcc.Store(id="history-store", data=[]),
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
                                className="stage-row",
                                children=[
                                    html.Div(
                                        className="card view-card",
                                        children=[
                                            html.Div("Field preview", className="card-title"),
                                            html.Div(
                                                "Extracellular potential at the cell plane — "
                                                "the cathodic well (red) depolarises cells.",
                                                className="card-hint",
                                            ),
                                            dcc.Graph(
                                                id="field-graph",
                                                config={
                                                    "displayModeBar": False,
                                                    "responsive": True,
                                                },
                                            ),
                                        ],
                                    ),
                                    html.Div(
                                        className="card result-card",
                                        children=[
                                            html.Div(
                                                "Selective operating window", className="card-title"
                                            ),
                                            dcc.Loading(
                                                html.Div(
                                                    html.Div(
                                                        "Set up a scene, then evaluate to find "
                                                        "the safe-and-selective amplitude window.",
                                                        className="scorecard-empty",
                                                    ),
                                                    id="scorecard-slot",
                                                ),
                                                type="dot",
                                                color=_ACCENT,
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                            html.Div(
                                className="card runs-card",
                                children=[
                                    html.Div("Recent runs", className="card-title"),
                                    html.Div(
                                        "Evaluate a few scenes and compare — click one to restore "
                                        "its settings.",
                                        className="card-hint",
                                    ),
                                    html.Div(
                                        _runs_strip(None), id="runs-strip", className="runs-strip"
                                    ),
                                ],
                            ),
                            _validation_panel(),
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
        Output("history-store", "data"),
        Input("evaluate-btn", "n_clicks"),
        State("layout", "value"),
        State("electrode-um", "value"),
        State("pitch-um", "value"),
        State("phase-width", "value"),
        State("neighbor-um", "value"),
        State("sigma", "value"),
        State("history-store", "data"),
        prevent_initial_call=True,
    )
    def _evaluate(
        _clicks, layout_value, electrode_um, pitch_um, phase_width, neighbor_um, sigma, history
    ):
        params = {
            "layout": layout_value,
            "electrode_um": electrode_um,
            "pitch_um": pitch_um,
            "phase_width": phase_width,
            "neighbor_um": neighbor_um,
            "sigma": sigma,
        }
        scene = build_scene(
            layout=layout_value,
            electrode_um=electrode_um,
            pitch_um=pitch_um,
            phase_width_us=phase_width,
            neighbor_um=neighbor_um,
            sigma_S_per_m=sigma,
        )
        result = evaluate(scene.patch, scene.array, scene.config, scene.conductivity)
        score = scorecard_data(result)
        history = ([{"params": params, "score": score}] + (history or []))[:_MAX_HISTORY]
        return _scorecard(score), history

    @app.callback(Output("runs-strip", "children"), Input("history-store", "data"))
    def _render_runs(history):
        return _runs_strip(history)

    @app.callback(
        Output("layout", "value"),
        Output("electrode-um", "value"),
        Output("pitch-um", "value"),
        Output("phase-width", "value"),
        Output("neighbor-um", "value"),
        Output("sigma", "value"),
        Input({"type": "run-card", "index": ALL}, "n_clicks"),
        State("history-store", "data"),
        prevent_initial_call=True,
    )
    def _restore(_clicks, history):
        trig = ctx.triggered_id
        if not isinstance(trig, dict) or not history:
            raise PreventUpdate
        if not ctx.triggered or not ctx.triggered[0].get("value"):
            raise PreventUpdate  # a re-render, not an actual click
        idx = trig.get("index")
        if idx is None or idx >= len(history):
            raise PreventUpdate
        p = history[idx]["params"]
        return (
            p["layout"],
            p["electrode_um"],
            p["pitch_um"],
            p["phase_width"],
            p["neighbor_um"],
            p["sigma"],
        )


def create_app() -> Dash:
    app = Dash(__name__, title="Retinode")
    app.layout = layout()
    register_callbacks(app)
    return app
