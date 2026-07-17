"""P7 S3b (fem): the conda-side FEM field solver the API dispatches to.

Runs in the ``retinode-fem`` env (DOLFINx). Imports ``api.fem_job`` — which works
here only because ``api/__init__`` is lazy (it doesn't pull FastAPI, absent from
this env). Verifies the solver produces a sane field grid for a Compare scene.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

from api.fem_job import solve_fem_grid  # noqa: E402

pytestmark = pytest.mark.fem


def test_fem_job_solves_a_flat_disk_field_grid():
    params = {
        "layout": "single",
        "electrode_um": 10.0,
        "pitch_um": 60.0,
        "phase_width_us": 200.0,
        "neighbor_um": 40.0,
        "sigma_S_per_m": 1.0,
        "extent_um": 130.0,
        "n": 15,  # small grid so the test is quick
    }
    grid = solve_fem_grid(params)
    ve = np.array(grid["ve_mV"])
    assert ve.shape == (15, 15)
    assert grid["vmax_mV"] > 0.0
    # a single cathode: the field is negative, deepest near the electrode axis (centre)
    assert ve.max() <= 1e-9
    assert ve[7, 7] == pytest.approx(ve.min(), rel=0.15)
    # finite everywhere and roughly the analytical order of magnitude (a few mV)
    assert np.all(np.isfinite(ve))
    assert 1.0 < abs(ve.min()) < 20.0
    assert not math.isnan(grid["vmax_mV"])
