"""P4 S2 (fast): the DOLFINx backend's cheap guards, no dolfinx needed.

The layered-conductivity rejection and the backend identity run before any
dolfinx import, so they belong in the fast suite; the solves themselves are in
test_fem_backend.py (fem)."""

from __future__ import annotations

import numpy as np
import pytest

from engine.field.backend import FieldBackend
from engine.field.fem_fenicsx import FenicsxBackend
from engine.field.mesh import FieldDomain
from engine.spec import ElectrodeArray, HomogeneousConductivity, LayeredConductivity
from engine.spec.conductivity import Layer
from engine.spec.geometry import Electrode


def _array() -> ElectrodeArray:
    return ElectrodeArray(
        electrodes=(Electrode(id="A", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )


def test_backend_satisfies_the_protocol_and_names_itself():
    backend: FieldBackend = FenicsxBackend()
    assert backend.name == "fem_fenicsx"


def test_anisotropic_layers_are_deferred():
    """Isotropic layers are supported (S3); diagonal anisotropy is not yet, and
    the refusal must fire before any mesh build or dolfinx import."""
    cond = LayeredConductivity(
        layers=(Layer(sigma_S_per_m=1.0, thickness_um=50.0, anisotropy=(1.0, 1.0, 0.5)),)
    )
    q = np.array([[0.0, 0.0, 20.0]])
    with pytest.raises(NotImplementedError, match="anisotrop"):
        FenicsxBackend().transfer_matrix(_array(), cond, q)


def test_solve_params_capture_the_mesh_and_degree():
    """The FEM cache identity (fed to field_key) must move whenever the mesh
    resolution/extent or the element degree changes, and be stable otherwise --
    computed without touching dolfinx."""
    arr, cond = _array(), HomogeneousConductivity(sigma_S_per_m=1.0)
    coarse = FenicsxBackend(domain=FieldDomain(arr, cond, 200.0, 200.0, 4.0, 50.0))
    fine = FenicsxBackend(domain=FieldDomain(arr, cond, 200.0, 200.0, 2.0, 50.0))
    deg2 = FenicsxBackend(domain=FieldDomain(arr, cond, 200.0, 200.0, 4.0, 50.0), degree=2)

    assert coarse.solve_params(arr, cond) != fine.solve_params(arr, cond)  # resolution
    assert coarse.solve_params(arr, cond) != deg2.solve_params(arr, cond)  # degree
    # deterministic for an identical domain
    same = FenicsxBackend(domain=FieldDomain(arr, cond, 200.0, 200.0, 4.0, 50.0))
    assert coarse.solve_params(arr, cond) == same.solve_params(arr, cond)
