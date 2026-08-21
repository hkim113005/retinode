"""Composite cache keys for field solves and evaluation results (Phase-0 design).

A result is identified by *everything* that could change it: the field solve
(backend + array + conductivity), the stimulus, the patch, the scorer version,
and the off-target definition it was measured against. Keys are built from spec
content hashes (hashing.py) with ``combine``, so equal inputs key equal and any
change yields a fresh key — the basis for a content-addressed store (Phase 2).
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import numpy as np

from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig
from engine.spec.hashing import combine, spec_hash

if TYPE_CHECKING:
    from engine.eval.offtarget import OffTargetSet


def query_points_digest(points: np.ndarray) -> str:
    """Stable content hash of a query-point array (the cell's segment centers).

    Coordinates are rounded to 1e-6 µm (sub-picometre, well below any meaningful
    geometric resolution) and taken little-endian, so the digest is identical
    across processes and architectures for the same placement.
    """
    arr = np.round(np.asarray(points, dtype=float), 6).astype("<f8")
    return hashlib.sha256(arr.tobytes()).hexdigest()


def field_key(
    array: ElectrodeArray,
    conductivity: ConductivityModel,
    backend_name: str,
    query_points: np.ndarray | None = None,
    *,
    solve_params: str | None = None,
) -> str:
    """Identity of a field solve: the transfer matrix depends only on these.

    ``query_points`` (the cell's segment centers) is where the field is sampled,
    so a *per-cell* transfer-matrix cache must include it — two placements of the
    same cell type under one array have different fields. It is optional so the
    regime-level key (used inside ``result_key``, where the patch hash already
    captures every cell's placement) stays unchanged.

    ``solve_params`` carries backend-specific settings that change ``A`` beyond
    the array and conductivity — for the FEM backend, the mesh resolution/extent
    and element degree (``FenicsxBackend.solve_params``). Threading it in means a
    coarse-mesh ``A`` is never silently reused for a finer mesh. The analytical
    backend has no such settings and passes ``None``, so its keys are unchanged.
    """
    parts = [backend_name, spec_hash(array), spec_hash(conductivity)]
    if solve_params is not None:
        parts.append(solve_params)
    if query_points is not None:
        parts.append(query_points_digest(query_points))
    return combine(*parts)


def result_key(
    array: ElectrodeArray,
    conductivity: ConductivityModel,
    config: StimConfig,
    patch: RetinalPatch,
    off_target_set: OffTargetSet,
    *,
    backend_name: str,
    evaluator_version: str,
    solve_params: str | None = None,
    eval_params: str | None = None,
) -> str:
    """Identity of a scored evaluation (the Phase-0 result-key formula).

    ``solve_params`` must be threaded through here for the same reason ``field_key``
    documents it: ``FenicsxBackend.name`` is the constant ``"fem_fenicsx"`` regardless
    of mesh/degree/extent, so two FEM solves that differ only in resolution would
    otherwise collide on one result key and a persisted store would serve the coarse
    result for a fine re-solve. ``None`` (analytical, which has no mesh) reproduces the
    previous key exactly, so analytical result keys are unchanged.

    ``eval_params`` (from :func:`engine.eval.safety.eval_params_digest`) carries the
    scoring parameters that are not part of the scene — the safety limits and the
    overlap policy/epsilon. They were absent, which broke the promise in this module's
    own docstring that a result is identified by everything that could change it: the
    same study re-run against one store with tighter safety limits was served the
    permissive-limit numbers, ceiling and usability inverted, with no re-evaluation.
    ``None`` (every parameter at its default) reproduces the previous key exactly."""
    parts = [
        field_key(array, conductivity, backend_name, solve_params=solve_params),
        spec_hash(config),
        spec_hash(patch),
        evaluator_version,
        spec_hash(off_target_set),
    ]
    if eval_params is not None:
        parts.append(eval_params)
    return combine(*parts)
