"""Dispatch a geometry sweep to the conda interpreter (P8 S4).

The API runs in the uv env (no DOLFINx); a geometry study must run on the FEM tier,
which lives in the ``retinode-fem`` conda env. This bridges the two: it runs
:mod:`api.study_job` in that interpreter, streaming the job's per-geometry progress
back over stderr (a study is minutes long, so the bar must move), and reads the
result from a temp file so gmsh/PETSc stdout noise can't corrupt it.

Mirrors :mod:`api.fem_worker`; shares its interpreter resolution.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile

from .fem_worker import fem_python
from .jobs import ProgressFn
from .models import StudyControls, StudyResult


def _drain_progress(line: str, report: ProgressFn) -> None:
    """Parse one stderr line; move the bar on ``@@P <frac> <msg>``, ignore noise."""
    if not line.startswith("@@P "):
        return
    try:
        _, frac, msg = line.split(" ", 2)
        report(float(frac), msg.rstrip())
    except (ValueError, IndexError):
        pass  # a malformed progress line is not worth failing the job over


def run_study_job(
    controls: StudyControls,
    report: ProgressFn,
    *,
    timeout_s: float = 1800.0,
    popen=subprocess.Popen,
) -> StudyResult:
    """Run the FEM study in the conda env and return its frontier.

    ``report`` is called as each geometry completes, driven by the subprocess's
    streamed progress. Raises with the tail of stderr if the job fails or the FEM
    interpreter is absent.
    """
    payload = json.dumps(controls.model_dump())
    with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=True) as out:
        try:
            proc = popen(
                [fem_python(), "-m", "api.study_job", out.name],
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                cwd=os.getcwd(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "the FEM env is not available (comparing geometry needs DOLFINx); "
                "set RETINODE_FEM_PYTHON or install env/fem-environment.yml"
            ) from exc

        proc.stdin.write(payload)
        proc.stdin.close()
        tail: list[str] = []
        for line in proc.stderr:  # streams live while the sweep runs
            if line.startswith("@@P "):
                _drain_progress(line, report)
            else:
                tail.append(line.rstrip())
        code = proc.wait(timeout=timeout_s)
        if code != 0:
            last = " / ".join(t for t in tail[-3:] if t)
            raise RuntimeError(f"FEM study failed: {last}" if last else "FEM study failed")
        out.seek(0)
        result = json.load(out)
    return StudyResult(**result)
