"""Dispatch a bodied-scene scorecard to the conda interpreter.

A shaped/3D electrode is FEM-only (the analytical tier is a point source blind to the
body), so its operating-window scorecard cannot run in the uv API env. This bridges
the two: it runs :mod:`api.score_job` in the ``retinode-fem`` interpreter, streaming
the job's progress back over stderr and reading the scorecard from a temp file so
gmsh/PETSc stdout noise can't corrupt it.

Mirrors :mod:`api.study_worker`; shares its interpreter resolution and watchdog shape.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
from typing import Any

from .fem_worker import fem_python
from .jobs import ProgressFn
from .models import SceneControls, ScorecardResponse


def _drain_progress(line: str, report: ProgressFn) -> None:
    """Move the bar on a ``@@P <frac> <msg>`` line; ignore gmsh/PETSc noise."""
    if not line.startswith("@@P "):
        return
    try:
        _, frac, msg = line.split(" ", 2)
        report(float(frac), msg.rstrip())
    except (ValueError, IndexError):
        pass


def run_score_job(
    controls: SceneControls,
    report: ProgressFn,
    *,
    timeout_s: float = 600.0,
    popen: Any = subprocess.Popen,
) -> ScorecardResponse:
    """Run the FEM scorecard in the conda env and return it.

    Raises with the tail of stderr if the job fails (an ``OverlapConflict`` from a
    penetrating body under the ``reject`` policy surfaces here) or the FEM interpreter
    is absent.
    """
    payload = json.dumps(controls.model_dump())
    with tempfile.NamedTemporaryFile("r+", suffix=".json", delete=True) as out:
        try:
            proc = popen(
                [fem_python(), "-m", "api.score_job", out.name],
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                text=True,
                cwd=os.getcwd(),
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "the FEM env is not available (scoring a 3D electrode needs DOLFINx); "
                "set RETINODE_FEM_PYTHON or install env/fem-environment.yml"
            ) from exc

        # A watchdog enforces the wall-clock bound and ALWAYS reaps the child: the
        # stderr read loop blocks until EOF (child exit), so a solve that hangs while
        # alive would never time out on its own — the timer kills it, closing stderr.
        timed_out = threading.Event()
        watchdog = threading.Timer(timeout_s, lambda: (timed_out.set(), proc.kill()))
        watchdog.start()
        try:
            proc.stdin.write(payload)
            proc.stdin.close()
            tail: list[str] = []
            for line in proc.stderr:
                if line.startswith("@@P "):
                    _drain_progress(line, report)
                else:
                    tail.append(line.rstrip())
            code = proc.wait()
        finally:
            watchdog.cancel()
            proc.kill()  # no-op if already dead; reaps an orphan on any error path

        if timed_out.is_set():
            raise RuntimeError(f"FEM scorecard timed out after {timeout_s:.0f}s")
        if code != 0:
            last = " / ".join(t for t in tail[-3:] if t)
            raise RuntimeError(f"FEM scorecard failed: {last}" if last else "FEM scorecard failed")
        out.seek(0)
        result = json.load(out)
    return ScorecardResponse(**result)
