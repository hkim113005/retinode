"""Subprocess entry: score a bodied (3D) scene on the FEM tier, emit the scorecard.

Runs in the conda ``retinode-fem`` env (the only one with DOLFINx *and* NEURON),
invoked by :mod:`api.score_worker` from the uv API env. A shaped/3D electrode is
FEM-only — the analytical tier is a point source blind to the body — so the Compare
scorecard for one cannot run in-process; it dispatches here.

Mirrors :mod:`api.fem_job` / :mod:`api.study_job`: scene controls as JSON on stdin,
the scorecard dict written to the file named in ``argv[1]`` (NOT stdout, which
gmsh/PETSc corrupt with banners). Progress streams to **stderr** as
``@@P <fraction> <message>`` lines the worker parses. Pydantic-free so it imports in
the FEM env (see :mod:`api.scorecard_core`).
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _emit_progress(fraction: float, message: str) -> None:
    print(f"@@P {fraction:.4f} {message}", file=sys.stderr, flush=True)


def _resolve_body(body_spec: dict[str, Any]) -> Any:
    """A contract body dict → an ``engine.spec`` body (primitives + CAD via gmsh)."""
    from .cad_store import resolve_body

    return resolve_body(body_spec)


def solve_scorecard(controls: dict[str, Any]) -> dict[str, Any]:
    """Build the bodied scene, solve the FEM field + NEURON thresholds, score it."""
    from app.scene import build_scene
    from engine.eval import evaluate
    from engine.field.fem_fenicsx import FenicsxBackend

    from .scorecard_core import scorecard_dict
    from .study_core import _query_reach_um

    body = _resolve_body(controls.get("body") or {"kind": "none"})
    scene = build_scene(
        layout=controls["layout"],
        electrode_um=controls["electrode_um"],
        pitch_um=controls["pitch_um"],
        phase_width_us=controls["phase_width_us"],
        neighbor_um=controls["neighbor_um"],
        sigma_S_per_m=controls["sigma_S_per_m"],
        body=body,
    )
    _emit_progress(0.1, "meshing the electrode and placing the population")
    # Floor the FEM domain to the cell reach (the axon of passage runs far past the
    # electrode), or the solve raises on a query point outside the mesh.
    backend = FenicsxBackend(min_half_width_um=_query_reach_um(scene.patch) * 1.15)
    _emit_progress(0.3, "solving the FEM field and searching thresholds")
    result = evaluate(
        scene.patch,
        scene.array,
        scene.config,
        scene.conductivity,
        backend=backend,
        overlap_policy=controls.get("overlap_policy", "reject"),
    )
    _emit_progress(0.95, "scoring the operating window")
    return scorecard_dict(result)


def main() -> None:
    controls = json.load(sys.stdin)
    result = solve_scorecard(controls)
    with open(sys.argv[1], "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
