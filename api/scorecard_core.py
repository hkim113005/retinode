"""The scorecard payload as a plain dict, shared by the uv service and the FEM job.

The conda ``retinode-fem`` env has no Pydantic (like :mod:`api.study_core` and
:mod:`api.fem_job`), so the FEM scorecard job cannot build a ``ScorecardResponse``.
This is the single source of truth for the field mapping as a JSON-serialisable dict;
:func:`api.service.scorecard_payload` wraps it as the Pydantic model in the uv env.
"""

from __future__ import annotations

from typing import Any


def scorecard_dict(result: Any) -> dict[str, Any]:  # an engine.eval EvaluationResult
    """Map an evaluation result to the scorecard wire fields (see
    ``api.models.ScorecardResponse``). ``activated=False`` collapses to just that flag
    plus the off-target hash; every other field is absent."""
    offtarget = getattr(result, "offtarget_hash", None)
    if not result.activated or result.window is None or result.sow is None:
        return {"activated": False, "offtarget_hash": offtarget}
    w, sow = result.window, result.sow
    return {
        "activated": True,
        "offtarget_hash": offtarget,
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
        "off_target_thresholds_uA": dict(result.thresholds.off_target_thresholds_uA),
        "limiting_off_id": sow.limiting_off_id,
    }
