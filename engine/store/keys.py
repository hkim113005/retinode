"""Composite cache keys for field solves and evaluation results (Phase-0 design).

A result is identified by *everything* that could change it: the field solve
(backend + array + conductivity), the stimulus, the patch, the scorer version,
and the off-target definition it was measured against. Keys are built from spec
content hashes (hashing.py) with ``combine``, so equal inputs key equal and any
change yields a fresh key — the basis for a content-addressed store (Phase 2).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig
from engine.spec.hashing import combine, spec_hash

if TYPE_CHECKING:
    from engine.eval.offtarget import OffTargetSet


def field_key(
    array: ElectrodeArray,
    conductivity: ConductivityModel,
    backend_name: str,
) -> str:
    """Identity of a field solve: the transfer matrix depends only on these."""
    return combine(backend_name, spec_hash(array), spec_hash(conductivity))


def result_key(
    array: ElectrodeArray,
    conductivity: ConductivityModel,
    config: StimConfig,
    patch: RetinalPatch,
    off_target_set: OffTargetSet,
    *,
    backend_name: str,
    evaluator_version: str,
) -> str:
    """Identity of a scored evaluation (the Phase-0 result-key formula)."""
    return combine(
        field_key(array, conductivity, backend_name),
        spec_hash(config),
        spec_hash(patch),
        evaluator_version,
        spec_hash(off_target_set),
    )
