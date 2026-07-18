"""Dispatch an FEM field solve to the conda interpreter (P7 S3b, D5).

The API runs in the uv env, which has no DOLFINx; the FEM solve lives in the
``retinode-fem`` conda env. This module bridges the two: it runs ``api.fem_job`` in
that interpreter as a subprocess (scene on stdin, result written to a temp file so
gmsh/PETSc stdout noise can't corrupt it), then computes the field's divergence from
the cheap analytical preview — the "how much did accuracy change?" note the UI shows.

The interpreter is ``$RETINODE_FEM_PYTHON`` or the default miniforge path. If it is
absent (e.g. a machine with no FEM env), the job fails with a clear message rather
than hanging.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

import numpy as np

from app.scene import build_scene

from .models import FieldGridResponse, SceneControls
from .service import field_grid_payload

_DEFAULT_FEM_PYTHON = "/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python"


def fem_python() -> str:
    return os.environ.get("RETINODE_FEM_PYTHON", _DEFAULT_FEM_PYTHON)


def _run_fem_job(controls: SceneControls, timeout_s: float, runner=subprocess.run) -> dict:
    """Invoke ``api.fem_job`` in the FEM interpreter; return its field-grid dict."""
    payload = controls.model_dump()
    with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=True) as out:
        proc = runner(
            [fem_python(), "-m", "api.fem_job", out.name],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            cwd=os.getcwd(),
        )
        if proc.returncode != 0:
            tail = " / ".join((proc.stderr or "").strip().splitlines()[-3:])
            raise RuntimeError(f"FEM solve failed: {tail}" if tail else "FEM solve failed")
        out.seek(0)
        return json.load(out)


def max_divergence_pct(fem: FieldGridResponse, controls: SceneControls) -> float:
    """Peak |FEM − analytical| / |analytical| (%) over the meaningful field (>5% of
    peak) — how far the accurate solve moved from the analytical preview."""
    scene = build_scene(
        layout=controls.layout,
        electrode_um=controls.electrode_um,
        pitch_um=controls.pitch_um,
        phase_width_us=controls.phase_width_us,
        neighbor_um=controls.neighbor_um,
        sigma_S_per_m=controls.sigma_S_per_m,
    )
    an = field_grid_payload(
        scene.array, scene.config, scene.conductivity, extent_um=controls.extent_um, n=controls.n
    )
    a = np.abs(np.asarray(an.ve_mV))
    f = np.abs(np.asarray(fem.ve_mV))
    mask = a > 0.05 * a.max()
    if not mask.any():
        return 0.0
    return float(100.0 * np.max(np.abs(f[mask] - a[mask]) / a[mask]))


def solve_accurate_field(
    controls: SceneControls, *, timeout_s: float = 180.0, runner=subprocess.run
) -> tuple[FieldGridResponse, float | None]:
    """Run the FEM solve and return its field plus its divergence from analytical.

    A bodied (3D) electrode has no analytical baseline — the point source is blind to
    the geometry — so the divergence is meaningless there and returned as ``None``
    (the UI simply shows the FEM field without an "accuracy changed by X%" note)."""
    grid = _run_fem_job(controls, timeout_s, runner=runner)
    field = FieldGridResponse(**grid)
    if controls.body.kind != "none":
        return field, None
    return field, max_divergence_pct(field, controls)
