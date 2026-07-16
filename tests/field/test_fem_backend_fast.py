"""P4 S2 (fast): the DOLFINx backend's cheap guards, no dolfinx needed.

The layered-conductivity rejection and the backend identity run before any
dolfinx import, so they belong in the fast suite; the solves themselves are in
test_fem_backend.py (fem)."""

from __future__ import annotations

import numpy as np
import pytest

from engine.field.backend import FieldBackend
from engine.field.fem_fenicsx import FenicsxBackend
from engine.spec import ElectrodeArray, LayeredConductivity
from engine.spec.conductivity import Layer
from engine.spec.geometry import Electrode


def _array() -> ElectrodeArray:
    return ElectrodeArray(
        electrodes=(Electrode(id="A", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )


def test_backend_satisfies_the_protocol_and_names_itself():
    backend: FieldBackend = FenicsxBackend()
    assert backend.name == "fem_fenicsx"


def test_layered_conductivity_is_deferred_to_s3():
    cond = LayeredConductivity(layers=(Layer(sigma_S_per_m=1.0, thickness_um=50.0),))
    q = np.array([[0.0, 0.0, 20.0]])
    with pytest.raises(NotImplementedError, match="S3"):
        FenicsxBackend().transfer_matrix(_array(), cond, q)
