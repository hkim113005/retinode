"""Field-physics reproductions for the validation report (fast, no NEURON).

Wraps the two deep field invariants — Green's-function reciprocity and far-field
decay — as :class:`Reproduction` records so they appear alongside the literature
reproductions in the validation report and the app's Validation panel.
"""

from __future__ import annotations

import math

import numpy as np

from engine import spec
from engine.field import AnalyticalBackend

from .reproduction import Reproduction

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


def _one(pos: tuple[float, float, float], size: float = 8.0) -> spec.ElectrodeArray:
    return spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=pos, shape="disk", size_um=size),)
    )


def reciprocity_holds() -> Reproduction:
    """Ve at B from a source at A equals Ve at A from a source at B."""
    be = AnalyticalBackend()
    pa, pb = (0.0, 0.0, -30.0), (60.0, 25.0, -30.0)
    ve_ab = be.transfer_matrix(_one(pa), COND, np.array([pb])).item()
    ve_ba = be.transfer_matrix(_one(pb), COND, np.array([pa])).item()
    return Reproduction(
        name="the field is reciprocal (G(a,b) = G(b,a))",
        source="quasi-static EM",
        passed=math.isclose(ve_ab, ve_ba, rel_tol=1e-9),
        measured=f"G(a,b) {ve_ab:.4e} vs G(b,a) {ve_ba:.4e}",
        criterion="reciprocal to 1e-9",
    )


def _exponent(array: spec.ElectrodeArray, weights: dict[str, float]) -> float:
    be = AnalyticalBackend()
    i = np.array([weights.get(e.id, 0.0) for e in array.electrodes])
    v1 = abs((be.transfer_matrix(array, COND, np.array([[200.0, 0.0, -30.0]])) @ i).item())
    v2 = abs((be.transfer_matrix(array, COND, np.array([[400.0, 0.0, -30.0]])) @ i).item())
    return math.log(v1 / v2) / math.log(2.0)


def far_field_decay() -> Reproduction:
    """A monopole's field falls as 1/r, a balanced dipole's as 1/r²."""
    monopole = _one((0.0, 0.0, 0.0), 6.0)
    dipole = spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(id="c", pos_um=(-8.0, 0.0, 0.0), shape="disk", size_um=6.0),
            spec.Electrode(id="a", pos_um=(8.0, 0.0, 0.0), shape="disk", size_um=6.0),
        )
    )
    n_mono = _exponent(monopole, {"e": -1.0})
    n_dip = _exponent(dipole, {"c": -1.0, "a": 1.0})
    passed = math.isclose(n_mono, 1.0, abs_tol=0.1) and math.isclose(n_dip, 2.0, abs_tol=0.2)
    return Reproduction(
        name="far-field decay (monopole 1/r, dipole 1/r²)",
        source="quasi-static EM",
        passed=passed,
        measured=f"monopole 1/r^{n_mono:.2f}, dipole 1/r^{n_dip:.2f}",
        criterion="monopole exponent ~1, dipole exponent ~2",
    )


def all_physics_reproductions() -> list[Reproduction]:
    return [reciprocity_holds(), far_field_decay()]
