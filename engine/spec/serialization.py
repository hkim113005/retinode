"""Canonical JSON serialization for the spec objects.

Round-trip contract: ``from_json(to_json(x)) == x`` for every spec object.

- **Canonical**: keys sorted, tight separators, ``allow_nan=False`` (NaN/Inf are
  validation errors, not serializable), so equal specs produce byte-identical
  JSON — which is what makes the content hash (see hashing.py) stable.
- **Self-describing**: each object carries a ``__type__`` tag, so the decoder
  rebuilds the exact class — including which arm of the ConductivityModel union
  a value is — without the caller passing the type in.
- **Type-directed decode**: JSON arrays become tuples (not lists) and nested
  objects become dataclasses, driven by each field's annotation, so the decoded
  value compares equal to the original frozen dataclass.
"""

from __future__ import annotations

import json
import types
import typing
from dataclasses import fields, is_dataclass
from functools import cache
from typing import Any

from .conductivity import HomogeneousConductivity, Layer, LayeredConductivity
from .geometry import Electrode, ElectrodeArray
from .patch import RGC, RetinalPatch
from .stim import StimConfig, Waveform
from .study import StudyDefinition, Sweep

# Name -> class, so a `__type__` tag decodes to the right dataclass.
_REGISTRY: dict[str, type] = {
    c.__name__: c
    for c in (
        Electrode,
        ElectrodeArray,
        Waveform,
        StimConfig,
        Layer,
        HomogeneousConductivity,
        LayeredConductivity,
        RGC,
        RetinalPatch,
        Sweep,
        StudyDefinition,
    )
}


@cache
def _hints(cls: type) -> dict[str, Any]:
    """Resolved field annotations (strings -> types), cached per class."""
    return typing.get_type_hints(cls)


# --- encode ----------------------------------------------------------------


def _encode(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {"__type__": type(obj).__name__}
        for f in fields(obj):
            out[f.name] = _encode(getattr(obj, f.name))
        return out
    if isinstance(obj, (tuple, list)):
        return [_encode(e) for e in obj]
    return obj  # str, int, float, bool, None


def to_json(obj: Any) -> str:
    """Serialize a spec object to canonical JSON."""
    return json.dumps(
        _encode(obj),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=False,
    )


# --- decode ----------------------------------------------------------------


def _decode_value(raw: Any, hint: Any) -> Any:
    if raw is None:
        return None

    origin = typing.get_origin(hint)

    # Every union field in the spec is Optional[X]; None is handled above, so
    # exactly one non-None arm remains. (The ConductivityModel union is only
    # ever top-level, decoded via its __type__ tag, not through here.) A
    # multi-arm union field would fail the unpack loudly rather than silently.
    if origin is typing.Union or origin is types.UnionType:
        (arm,) = [a for a in typing.get_args(hint) if a is not type(None)]
        return _decode_value(raw, arm)

    # Tuples: variadic tuple[X, ...] or fixed tuple[X, Y, Z].
    if origin is tuple:
        args = typing.get_args(hint)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode_value(e, args[0]) for e in raw)
        return tuple(_decode_value(e, t) for e, t in zip(raw, args, strict=False))

    # Nested dataclass carried as a tagged dict.
    if isinstance(raw, dict) and "__type__" in raw:
        return _decode_obj(raw)

    return raw  # primitives, Literal strings, bool, int


def _decode_obj(d: dict[str, Any]) -> Any:
    cls = _REGISTRY[d["__type__"]]
    hints = _hints(cls)
    # Only pass fields present in the payload, so missing ones fall back to
    # dataclass defaults (forward-compatible with older serialized specs).
    kwargs = {f.name: _decode_value(d[f.name], hints[f.name]) for f in fields(cls) if f.name in d}
    return cls(**kwargs)


def from_json(s: str) -> Any:
    """Deserialize canonical JSON back into the spec object it came from."""
    return _decode_obj(json.loads(s))
