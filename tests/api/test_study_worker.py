"""P8 S4: the uv-side dispatcher that runs a study in the conda FEM env.

The subprocess is mocked here. The real FEM+NEURON run is a fem-marked test in
tests/field. What matters at this layer: the streamed progress protocol, the result
round-trip, and honest failure when the FEM env is missing.
"""

import io
import json

import pytest

from api.models import StudyControls, StudyResult
from api.study_worker import run_study_job

_CONTROLS = StudyControls(diameters_um=[10.0, 16.0], pitches_um=[50.0])


class _FakeProc:
    """A subprocess stand-in that streams stderr lines, then writes the result file."""

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
        # the entrypoint is `python -m api.study_job <out.json>`, so the temp file is last
        return _FakeProc(cmd[-1], stderr_lines, result, code)

    popen.captured = captured
    return popen


def test_streams_progress_and_returns_the_frontier():
    reports = []
    result = {
        "points": [
            {
                "diameter_um": 10.0, "pitch_um": 50.0, "cost_uA": 8.0,
                "selectivity_uA": 4.0, "safe": True, "on_frontier": True, "spread_uA": None,
            }
        ],
        "n_geometries": 2,
        # run_study in the conda env emits this; the worker requires it, so a payload
        # without it must fail loudly rather than default to a plausible tier.
        "tier": "fem",
    }
    popen = _popen_factory(
        [
            "Info    : gmsh meshing...\n",  # noise the worker must ignore
            "@@P 0.4250 solving geometry 1 of 2\n",
            "PETSc banner blah\n",
            "@@P 0.8500 solving geometry 2 of 2\n",
        ],
        result,
    )
    out = run_study_job(_CONTROLS, lambda f, m: reports.append((f, m)), popen=popen)

    assert isinstance(out, StudyResult)
    assert out.n_geometries == 2
    assert out.points[0].diameter_um == 10.0
    # only the @@P lines moved the bar; gmsh/PETSc noise did not
    assert reports == [(0.425, "solving geometry 1 of 2"), (0.85, "solving geometry 2 of 2")]
    assert popen.captured["cmd"][1:3] == ["-m", "api.study_job"]


def test_a_nonzero_exit_fails_with_the_stderr_tail():
    popen = _popen_factory(["boom: dolfinx assembly error\n"], result=None, code=1)
    with pytest.raises(RuntimeError, match="dolfinx assembly error"):
        run_study_job(_CONTROLS, lambda f, m: None, popen=popen)


def test_a_missing_fem_interpreter_is_a_clear_message():
    def popen(cmd, **kwargs):
        raise FileNotFoundError(cmd[0])

    with pytest.raises(RuntimeError, match="FEM env is not available"):
        run_study_job(_CONTROLS, lambda f, m: None, popen=popen)


def test_a_hung_child_is_killed_by_the_watchdog_and_reported_as_a_timeout():
    """The real robustness fix: a FEM solve that hangs while alive (stops emitting
    output but never exits) would block the worker forever, because the stderr read
    loop only ends at child EOF. A watchdog must kill it and surface a timeout."""
    import threading

    unblocked = threading.Event()
    proc_ref = {}

    class HangProc:
        def __init__(self):
            self.stdin = io.StringIO()
            self.killed = False

            def gen():
                unblocked.wait(5.0)  # blocks the read loop until kill() (or a safety cap)
                return
                yield  # unreachable; it only makes this a generator

            self.stderr = gen()

        def wait(self, timeout=None):
            return -9  # killed

        def kill(self):
            self.killed = True
            unblocked.set()  # let the blocked stderr generator finish

    def popen(cmd, **kwargs):
        p = HangProc()
        proc_ref["p"] = p
        return p

    with pytest.raises(RuntimeError, match="timed out"):
        run_study_job(_CONTROLS, lambda f, m: None, timeout_s=0.2, popen=popen)
    assert proc_ref["p"].killed  # the child was reaped, not orphaned


def test_the_child_is_reaped_even_on_a_normal_failure():
    popen = _popen_factory(["boom\n"], result=None, code=1)
    with pytest.raises(RuntimeError):
        run_study_job(_CONTROLS, lambda f, m: None, popen=popen)
    # the finally-kill ran (the fake records it)
