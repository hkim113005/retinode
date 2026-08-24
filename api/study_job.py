"""Subprocess entry: run a full geometry sweep on the FEM tier, emit JSON.

Runs in the conda ``retinode-fem`` env (the only one with DOLFINx *and* NEURON),
invoked by :mod:`api.study_worker` from the uv API env. Reads the study controls as
JSON on stdin and writes ``{points, n_geometries}`` to the file named in ``argv[1]``.
NOT stdout: gmsh/PETSc scribble banners there and would corrupt the JSON.

Progress streams to **stderr** as ``@@P <fraction> <message>`` lines, which the uv
worker parses to move the job's progress bar (a study is minutes long); any other
stderr line is noise to be ignored or shown only on failure.

FastAPI- and Pydantic-free (see :mod:`api.study_core`), so it imports in the FEM env.
"""

from __future__ import annotations

import json
import sys

from api.study_core import run_study


def _emit_progress(fraction: float, message: str) -> None:
    # a sentinel prefix the worker can pick out of gmsh/PETSc stderr noise
    print(f"@@P {fraction:.4f} {message}", file=sys.stderr, flush=True)


def main() -> None:
    controls = json.load(sys.stdin)
    result = run_study(controls, on_progress=_emit_progress)
    with open(sys.argv[1], "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
