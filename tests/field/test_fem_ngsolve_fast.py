"""P4 S5 (fast): the NGSolve backend's cheap guards, no ngsolve needed."""

from __future__ import annotations

import numpy as np
import pytest

from engine.field.backend import FieldBackend
from engine.field.fem_ngsolve import NGSolveBackend
from engine.spec import ElectrodeArray, LayeredConductivity
from engine.spec.conductivity import Layer
from engine.spec.geometry import Electrode


def _array() -> ElectrodeArray:
    return ElectrodeArray(
        electrodes=(Electrode(id="A", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )


def test_backend_satisfies_the_protocol_and_names_itself():
    backend: FieldBackend = NGSolveBackend()
    assert backend.name == "fem_ngsolve"


def test_anisotropic_layers_are_deferred():
    cond = LayeredConductivity(
        layers=(Layer(sigma_S_per_m=1.0, thickness_um=50.0, anisotropy=(1.0, 1.0, 0.5)),)
    )
    q = np.array([[0.0, 0.0, 20.0]])
    with pytest.raises(NotImplementedError, match="anisotrop"):
        NGSolveBackend().transfer_matrix(_array(), cond, q)
