"""The uv-side dispatcher that scores a bodied (3D) scene in the conda FEM env.

The subprocess is mocked here — the real FEM+NEURON scorecard is a fem-marked test in
tests/field. What matters at this layer: the streamed progress protocol, the scorecard
round-trip, and honest failure (a missing FEM env, or an OverlapConflict surfaced from
the child's stderr)."""

import io
import json

import pytest

from api.models import CylinderBody, SceneControls, ScorecardResponse
from api.score_worker import run_score_job

_CONTROLS = SceneControls(body=CylinderBody(radius_um=5.0, height_um=30.0, conductive_faces="tip"))


class _FakeProc:
    def __init__(self, out_path, stderr_lines, result, code=0):
        self._out_path = out_path
        self._result = result
        self._code = code
        self.stdin = io.StringIO()
        self.stderr = iter(stderr_lines)
        self.killed = False

    def wait(self, timeout=None):
        if self._result is not None:
            with open(self._out_path, "w") as f:
                json.dump(self._result, f)
        return self._code

    def kill(self):
        self.killed = True


def _popen_factory(stderr_lines, result, code=0):
    captured = {}

    def popen(cmd, **kwargs):
        captured["cmd"] = cmd
        return _FakeProc(cmd[-1], stderr_lines, result, code)

    popen.captured = captured
    return popen


def test_streams_progress_and_returns_the_scorecard():
    reports = []
    result = {
        "activated": True, "target_uA": 7.83, "off_min_uA": 13.88, "ratio": 1.77,
        "window_lo_uA": 7.83, "window_hi_uA": 13.88, "usable_margin_uA": 6.05,
        "usable": True, "limiting": "off_target", "safety_ceiling_uA": 24.92,
        "safe_at_target": True, "off_target_thresholds_uA": {"neighbor": 13.88},
        "limiting_off_id": "neighbor",
    }
    popen = _popen_factory(
        [
            "Info    : gmsh meshing...\n",  # noise the worker must ignore
            "@@P 0.3000 solving the FEM field\n",
            "PETSc banner blah\n",
            "@@P 0.9500 scoring the operating window\n",
        ],
        result,
    )
    out = run_score_job(_CONTROLS, lambda f, m: reports.append((f, m)), popen=popen)

    assert isinstance(out, ScorecardResponse)
    assert out.activated and out.target_uA == 7.83 and out.usable_margin_uA == 6.05
    assert reports == [(0.3, "solving the FEM field"), (0.95, "scoring the operating window")]
    assert popen.captured["cmd"][1:3] == ["-m", "api.score_job"]


def test_an_overlap_conflict_surfaces_from_the_stderr_tail():
    popen = _popen_factory(
        ["engine.eval.overlap.OverlapConflict: cell 'target' has 2 compartment(s) inside\n"],
        result=None,
        code=1,
    )
    with pytest.raises(RuntimeError, match="OverlapConflict"):
        run_score_job(_CONTROLS, lambda f, m: None, popen=popen)


def test_a_missing_fem_interpreter_is_a_clear_message():
    def popen(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    with pytest.raises(RuntimeError, match="FEM env is not available"):
        run_score_job(_CONTROLS, lambda f, m: None, popen=popen)


def test_a_hung_child_is_killed_by_the_watchdog():
    import threading

    unblocked = threading.Event()
    proc_ref = {}

    class HangProc:
        def __init__(self):
            self.stdin = io.StringIO()
            self.killed = False

            def gen():
                unblocked.wait(5.0)
                return
                yield

            self.stderr = gen()

        def wait(self, timeout=None):
            return -9

        def kill(self):
            self.killed = True
            unblocked.set()

    def popen(cmd, **kwargs):
        p = HangProc()
        proc_ref["p"] = p
        return p

    with pytest.raises(RuntimeError, match="timed out"):
        run_score_job(_CONTROLS, lambda f, m: None, timeout_s=0.2, popen=popen)
    assert proc_ref["p"].killed
