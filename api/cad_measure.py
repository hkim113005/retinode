"""Measure an uploaded CAD solid in the conda FEM env.

Reading a STEP/BREP needs gmsh, which lives only in the FEM env, so the uv API
process cannot describe an uploaded solid at all. That is why the Compare screen's 3D
loupe used to draw a flat disk for a CAD electrode: not a rendering bug, simply no
dimensions to draw with.

This runs one short subprocess at upload time (~0.5 s including interpreter start,
measured on a 5 x 30 um pillar) and caches the answer beside the file, so every later
gmsh-free request can describe the shape without paying that cost again.

Best-effort by construction: if the FEM env is absent the upload still succeeds and the
client simply gets no dimensions, the same graceful degradation the loupe already
handles. A CAD upload must never fail because the *preview* could not be measured.
"""

from __future__ import annotations

import json
import subprocess

from .cad_store import read_dims, resolve_upload, store_dims
from .fem_worker import fem_python

# Printed on stdout by the child. gmsh chatters on stdout, so the payload is fenced by
# a marker the parent scans for rather than trusting the last line.
_MARK = "@@DIMS "

_CHILD = f"""
import json, sys
from engine.field.mesh3d import load_cad_body
b = load_cad_body(sys.argv[1])
print({_MARK!r} + json.dumps({{
    "bounding_radius_um": b.bounding_radius_um,
    "bounding_height_um": b.bounding_height_um,
    "surface_area_um2": b.surface_area_um2,
}}))
"""


def measure_upload(upload_id: str, *, timeout_s: float = 60.0) -> dict[str, float] | None:
    """Measure a stored CAD solid, caching and returning its dimensions.

    Returns the cached value if present. Returns None (never raises) when the FEM
    env is unavailable, the solid is unreadable, or the measurement times out; the
    caller degrades to "shape not previewable" rather than failing the upload.
    """
    cached = read_dims(upload_id)
    if cached is not None:
        return cached
    try:
        path = resolve_upload(upload_id)
    except Exception:
        return None
    try:
        proc = subprocess.run(
            [fem_python(), "-c", _CHILD, path],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None  # no FEM env, or it died; the upload stands regardless
    for line in proc.stdout.splitlines():
        if line.startswith(_MARK):
            try:
                dims = json.loads(line[len(_MARK) :])
            except ValueError:
                return None
            if isinstance(dims, dict):
                store_dims(upload_id, dims)
                return dims
    return None
