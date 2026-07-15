"""Tagged-JSON (de)serialization for evaluation results — the JSON sidecars.

Mirrors ``engine.spec.serialization`` (``__type__``-tagged, type-directed decode
so tuples decode as tuples and nested dataclasses as their exact class) but for
the *result* dataclass tree, which the spec serializer does not cover. Two
differences matter:

- **Inf is allowed.** A selective window with no off-target has ``off_min = inf``;
  an unbounded safety ceiling is ``inf`` too. ``allow_nan=True`` writes these as
  ``Infinity`` tokens that ``json.loads`` reads straight back (Python-JSON, not
  strict JSON — fine for an internal sidecar).
- **Plain dicts are carried through.** ``PopulationThresholds`` holds a
  ``dict[str, float]`` off-target map; it is preserved as a mapping, not mistaken
  for a tagged object.
"""

from __future__ import annotations

import json
import types
import typing
from dataclasses import fields, is_dataclass
from functools import cache
from typing import Any

from engine.cable.population import PopulationThresholds
from engine.eval.metrics import SOW
from engine.eval.result import EvaluationResult, OperatingWindow
from engine.eval.safety import ElectrodeSafety, SafetyReport

_REGISTRY: dict[str, type] = {
    c.__name__: c
    for c in (
        EvaluationResult,
        OperatingWindow,
        SOW,
        SafetyReport,
        ElectrodeSafety,
        PopulationThresholds,
    )
}


@cache
def _hints(cls: type) -> dict[str, Any]:
    return typing.get_type_hints(cls)


def _encode(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {"__type__": type(obj).__name__}
        for f in fields(obj):
            out[f.name] = _encode(getattr(obj, f.name))
        return out
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    if isinstance(obj, (tuple, list)):
        return [_encode(e) for e in obj]
    return obj  # str, int, float (incl. inf), bool, None


def dumps(result: EvaluationResult) -> str:
    """Serialize an EvaluationResult to a canonical, inf-tolerant JSON string."""
    return json.dumps(
        _encode(result),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=True,
        ensure_ascii=False,
    )


def _decode_value(raw: Any, hint: Any) -> Any:
    if raw is None:
        return None
    origin = typing.get_origin(hint)

    if origin is typing.Union or origin is types.UnionType:
        arms = [a for a in typing.get_args(hint) if a is not type(None)]
        if len(arms) == 1:
            return _decode_value(raw, arms[0])
        if isinstance(raw, dict) and "__type__" in raw:
            return _decode_obj(raw)
        return raw

    if origin is tuple:
        args = typing.get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode_value(e, args[0]) for e in raw)
        return tuple(_decode_value(e, t) for e, t in zip(raw, args, strict=False))

    if origin is dict:
        args = typing.get_args(hint)
        vt = args[1] if len(args) == 2 else Any
        return {k: _decode_value(v, vt) for k, v in raw.items()}

    if isinstance(raw, dict) and "__type__" in raw:
        return _decode_obj(raw)

    return raw


def _decode_obj(d: dict[str, Any]) -> Any:
    cls = _REGISTRY[d["__type__"]]
    hints = _hints(cls)
    kwargs = {f.name: _decode_value(d[f.name], hints[f.name]) for f in fields(cls) if f.name in d}
    return cls(**kwargs)


def loads(s: str) -> EvaluationResult:
    """Deserialize a result JSON sidecar back into the exact EvaluationResult."""
    obj = _decode_obj(json.loads(s))
    if not isinstance(obj, EvaluationResult):
        raise ValueError(f"expected an EvaluationResult, got {type(obj).__name__}")
    return obj
