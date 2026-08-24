"""Content-addressed store for uploaded CAD solids.

Two processes touch a CAD upload: the uv API receives it (``POST /cad``) and writes
it here; a conda FEM job later loads it with gmsh. They share this store on disk, so
the same ``upload_id`` resolves to the same path in both. Pydantic-free so the conda
jobs can import it (like :mod:`api.study_core`).

The id is the file's content hash plus its suffix, so re-uploading the same solid is
idempotent and the loader still sees the format. The store lives under a temp dir
(override with ``RETINODE_CAD_DIR``); it is a cache, not a system of record.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import tempfile
from typing import Any

# STEP/BREP are OpenCASCADE solids that boolean-cut cleanly. STL is a surface
# tessellation, not a solid, and is rejected with a message that says so.
ALLOWED_SUFFIXES = (".step", ".stp", ".brep")
MAX_BYTES = 25 * 1024 * 1024


class CadUploadError(ValueError):
    """A rejected upload (bad format, too large, empty) or an unresolvable id."""


def _store_dir() -> pathlib.Path:
    default = pathlib.Path(tempfile.gettempdir()) / "retinode-cad"
    return pathlib.Path(os.environ.get("RETINODE_CAD_DIR", str(default)))


def store_upload(filename: str, content: bytes) -> tuple[str, str]:
    """Validate and store an uploaded CAD file; return ``(upload_id, clean_name)``."""
    suffix = pathlib.Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise CadUploadError(
            f"unsupported CAD format {suffix or '(none)'!r}; use STEP or BREP "
            "(STL is a surface mesh, not a solid, and can't be cut cleanly)"
        )
    if not content:
        raise CadUploadError("the uploaded CAD file is empty")
    if len(content) > MAX_BYTES:
        raise CadUploadError(f"CAD file too large ({len(content)} bytes > {MAX_BYTES})")
    digest = hashlib.sha256(content).hexdigest()[:16]
    upload_id = f"{digest}{suffix}"
    store = _store_dir()
    store.mkdir(parents=True, exist_ok=True)
    path = store / upload_id
    if not path.exists():  # content-addressed: identical bytes reuse the same file
        path.write_bytes(content)
    return upload_id, pathlib.Path(filename).name


def resolve_upload(upload_id: str) -> str:
    """Resolve an ``upload_id`` to its on-disk path (raises if unknown/malformed)."""
    if not upload_id or "/" in upload_id or "\\" in upload_id or ".." in upload_id:
        raise CadUploadError(f"invalid CAD upload id {upload_id!r}")
    path = _store_dir() / upload_id
    if not path.exists():
        raise CadUploadError(f"unknown CAD upload {upload_id!r}; re-upload the file")
    return str(path)


def resolve_body(body_spec: dict[str, Any]) -> Any:  # an engine.spec ElectrodeBody | None
    """A contract body dict → an ``engine.spec`` body. Primitives resolve via the
    pure ``app.scene`` helper; a CAD body is loaded with gmsh from its stored upload
    (conda env only). This is the single body-resolution path the FEM jobs share."""
    from app.scene import body_from_spec

    if body_spec.get("kind") == "cad":
        from engine.field.mesh3d import load_cad_body

        return load_cad_body(
            resolve_upload(body_spec["upload_id"]),
            conductive_faces=body_spec.get("conductive_faces", "all"),
        )
    return body_from_spec(body_spec)


# --- cached dimensions, so the gmsh-free API can describe the solid ----------------
#
# Reading a STEP needs gmsh, which lives only in the conda FEM env, so ``POST
# /compare`` (uv env) could not describe an uploaded solid at all, and the 3D loupe
# fell back to drawing a flat disk for it. Measuring once at upload and caching the
# result next to the file lets every later gmsh-free request describe the shape.
#
# Content-addressed like the solid itself: the id already includes the file's hash, so
# a cached measurement can never belong to different bytes.

_DIMS_SUFFIX = ".dims.json"


def dims_path(upload_id: str) -> str:
    """Sidecar path for an upload's cached dimensions (same traversal guard)."""
    return resolve_upload(upload_id) + _DIMS_SUFFIX


def store_dims(upload_id: str, dims: dict[str, float]) -> None:
    """Cache an upload's measured dimensions. Best-effort: a failure here must never
    fail the upload, which has already succeeded."""
    try:
        pathlib.Path(dims_path(upload_id)).write_text(json.dumps(dims))
    except (OSError, CadUploadError):
        pass


def read_dims(upload_id: str) -> dict[str, float] | None:
    """An upload's cached dimensions, or None if it was never measured (no FEM env at
    upload time, or an older upload). Callers must degrade rather than fail."""
    try:
        raw = pathlib.Path(dims_path(upload_id)).read_text()
    except (OSError, CadUploadError):
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    return d if isinstance(d, dict) else None
