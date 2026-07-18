"""Subprocess entry: solve an FEM field grid for a Compare scene, emit JSON.

This runs in the **conda** ``retinode-fem`` env (the only one with DOLFINx), invoked
by :mod:`api.fem_worker` in the uv API env. It reads the scene controls as JSON on
stdin and writes ``{xs_um, ys_um, ve_mV, vmax_mV}`` to the file named in ``argv[1]``
— NOT stdout, because gmsh/PETSc scribble banners there and would corrupt the JSON
(see ``main`` below). Plain dicts, no FastAPI, so it imports cleanly in the FEM env
(see the lazy ``api/__init__``).

The FEM tissue is the ``z >= 0`` slab, so the field is sampled at ``+|cell depth|``
(the analytical tier is mirror-symmetric across ``z = 0``, so this is the same
physical plane the ``/compare`` preview shows).
"""

from __future__ import annotations

import json
import sys
from typing import Any

import numpy as np


def solve_fem_grid(params: dict[str, Any]) -> dict[str, Any]:
    """Solve the DOLFINx field for the scene on the query grid. Conda env only."""
    from app.scene import build_scene, cell_depth_um
    from engine.field import current_vector, mesh
    from engine.field.fem_fenicsx import FenicsxBackend

    scene = build_scene(
        layout=params["layout"],
        electrode_um=params["electrode_um"],
        pitch_um=params["pitch_um"],
        phase_width_us=params["phase_width_us"],
        neighbor_um=params["neighbor_um"],
        sigma_S_per_m=params["sigma_S_per_m"],
    )
    extent = float(params.get("extent_um", 130.0))
    n = int(params.get("n", 61))  # match SceneControls.n, so the grid shape agrees
    # with the analytical grid the divergence is measured against
    z = cell_depth_um()  # the cell plane, in the z>=0 tissue the FEM domain meshes

    xs = np.linspace(-extent, extent, n)
    ys = np.linspace(-extent, extent, n)
    xx, yy = np.meshgrid(xs, ys)
    points = np.column_stack([xx.ravel(), yy.ravel(), np.full(xx.size, z)])

    # A domain much larger than the sampled grid so the grounded truncation stays
    # well outside the near field (the analytical tier it is compared against is an
    # infinite half-space). Fine at the electrode, coarse far away. Still truncation-
    # sensitive — the residual FEM/analytical difference is real (finite electrode +
    # bounded domain), which is exactly what the "accurate" pass surfaces.
    domain = mesh.FieldDomain(
        array=scene.array,
        conductivity=scene.conductivity,
        half_width_um=max(1500.0, extent * 8.0),
        depth_um=600.0,
        h_electrode_um=3.0,
        h_far_um=100.0,
    )
    a = FenicsxBackend(domain=domain).transfer_matrix(scene.array, scene.conductivity, points)
    ve = (a @ current_vector(scene.array, scene.config)).reshape(n, n)
    return {
        "xs_um": xs.tolist(),
        "ys_um": ys.tolist(),
        "ve_mV": ve.tolist(),
        "vmax_mV": float(np.abs(ve).max()) or 1.0,
    }


def main() -> None:
    # Write the result to the file named in argv[1], NOT stdout: gmsh/PETSc print
    # progress banners to stdout, which would corrupt a JSON-on-stdout protocol.
    params = json.load(sys.stdin)
    result = solve_fem_grid(params)
    with open(sys.argv[1], "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
