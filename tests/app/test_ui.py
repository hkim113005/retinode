"""P2b: the layout builds and the scorecard renders both outcomes (smoke)."""

from typing import Any

from app.ui import _scorecard, create_app, layout


def _collect_ids(node: Any) -> set[str]:
    ids: set[str] = set()
    if node is None or isinstance(node, (str, int, float, bool)):
        return ids
    cid = getattr(node, "id", None)
    if isinstance(cid, str):
        ids.add(cid)
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            ids |= _collect_ids(c)
    else:
        ids |= _collect_ids(children)
    return ids


def test_layout_wires_every_control_id():
    ids = _collect_ids(layout())
    expected = {
        "layout",
        "electrode-um",
        "pitch-um",
        "phase-width",
        "neighbor-um",
        "sigma",
        "evaluate-btn",
        "field-graph",
        "scorecard-slot",
    }
    assert expected <= ids


def test_create_app_builds():
    app = create_app()
    assert app.title == "Retinode"
    assert app.layout is not None


def test_scorecard_renders_usable_and_blocked():
    base = {
        "activated": True,
        "target_uA": 8.0,
        "off_min_uA": 10.0,
        "ratio": 1.25,
        "window_lo_uA": 8.0,
        "window_hi_uA": 10.0,
        "usable_margin_uA": 2.0,
        "limiting": "off_target",
        "safety_ceiling_uA": 24.0,
        "safe_at_target": True,
    }
    assert "usable" in _collect_classes(_scorecard({**base, "usable": True}))
    assert "blocked" in _collect_classes(_scorecard({**base, "usable": False}))
    # a non-activated result renders the empty state, not a crash
    assert _scorecard({"activated": False}) is not None


def _collect_classes(node: Any) -> str:
    classes = getattr(node, "className", "") or ""
    children = getattr(node, "children", None)
    if isinstance(children, (list, tuple)):
        for c in children:
            classes += " " + _collect_classes(c)
    elif children is not None:
        classes += " " + _collect_classes(children)
    return classes
