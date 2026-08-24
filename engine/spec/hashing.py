"""Content hashing for spec objects and composite cache keys.

A spec's identity is its canonical JSON (serialization.py), so its content hash
is simply SHA-256 of that JSON: equal specs hash equal, any field change yields
a new hash, and the digest is stable across processes and machines (nothing
depends on dict ordering, memory addresses, or float repr quirks). Composite
keys, meaning the field and result keys of the store, are built from these
digests with ``combine``.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .serialization import to_json


def spec_hash(obj: Any) -> str:
    """SHA-256 hex digest of a spec object's canonical JSON."""
    return hashlib.sha256(to_json(obj).encode("utf-8")).hexdigest()


def combine(*parts: str) -> str:
    """Order-sensitive digest of several string parts (e.g. spec hashes plus a
    backend name and parameters), for composite cache keys.

    The parts are encoded as a canonical JSON array before hashing, so the
    boundaries between parts are unambiguous: no part's contents can forge a
    delimiter to collide with a different split.
    """
    payload = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
