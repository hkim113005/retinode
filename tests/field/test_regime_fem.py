"""P4 S5 (fem): the real analytical-vs-FEM regime map.

Demonstrates the decision the map exists to support: the analytical (homogeneous)
tier is trustworthy only near contrast 1 (an actually-homogeneous medium); once a
buried layer is meaningfully more or less conductive, the error is tens of
percent and the field must be escalated to FEM."""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

from engine.field.regime import regime_map  # noqa: E402
from engine.spec import ElectrodeArray  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem


def test_analytical_is_trustworthy_only_near_a_homogeneous_medium():
    arr = ElectrodeArray(
        electrodes=(Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 30.0], [0.0, 0.0, 40.0]])  # inside layer 1

    rm = regime_map(
        arr, q, sigma1_S_per_m=1.0, contrasts=[1.0, 0.3, 3.0],
        layer_thickness_um=50.0, half_width_um=2000.0, depth_um=2000.0,
        h_electrode_um=4.0, h_far_um=300.0, tol=0.1, degree=1,
    )

    by_contrast = {p.contrast: p for p in rm.points}
    # contrast 1 == homogeneous: only the small FEM/analytical discretization floor
    assert by_contrast[1.0].rel_error < 0.08
    assert by_contrast[1.0].trustworthy
    # a resistive (0.3) or conductive (3.0) buried layer: large error, escalate to FEM
    assert by_contrast[0.3].rel_error > 0.15
    assert by_contrast[3.0].rel_error > 0.15
    assert not by_contrast[0.3].trustworthy
    assert not by_contrast[3.0].trustworthy

    assert rm.trustworthy_contrasts == (1.0,)
