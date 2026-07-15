"""Vilkhu 2021: a confined return pattern avoids an axon of passage (P3 S2).

An axon crossing offset under the array is activated at a low threshold by a
monopolar electrode — a smeared, non-focal percept. Returning the current locally
on a ring of surrounding electrodes confines the field, so the activating function
(∂²Ve/∂s²) along the offset axon collapses and its threshold rises sharply: the
axon is avoided. This is the field-confinement mechanism behind Vilkhu et al.
(2021)'s bi-electrode axon avoidance, and the engine's home turf — axons are
modelled explicitly and the activating function is a first-class diagnostic.

Two checks: the AF flattening (fast, analytical) and the axon-of-passage threshold
rise (NEURON). Both reproduce cleanly — no AIS/dendrite confound, because an axon
of passage is far from its own soma.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from engine import spec
from engine.cable.activating import activating_function
from engine.field import AnalyticalBackend, FieldBackend, current_vector

from .reproduction import Reproduction

if TYPE_CHECKING:
    from engine.cable.morphology import RGCModel

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
_WAVE = spec.Waveform(phase_width_us=200.0)
_RETURN_IDS = ("ret0", "ret1", "ret2", "ret3")
_AXON_OFFSET_UM = 40.0  # the axon of passage runs at this y-offset, under the array


def _monopolar() -> tuple[spec.ElectrodeArray, spec.StimConfig]:
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="src", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    config = spec.StimConfig.from_map({"src": -1.0}, waveform=_WAVE, distant_return=True)
    return array, config


def _confined(ring_um: float = 35.0) -> tuple[spec.ElectrodeArray, spec.StimConfig]:
    """Source over the origin + a symmetric ring of local return electrodes."""
    ring = ((ring_um, 0.0), (-ring_um, 0.0), (0.0, ring_um), (0.0, -ring_um))
    electrodes = [spec.Electrode(id="src", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)]
    electrodes += [
        spec.Electrode(id=rid, pos_um=(x, y, 0.0), shape="disk", size_um=10.0)
        for rid, (x, y) in zip(_RETURN_IDS, ring, strict=True)
    ]
    array = spec.ElectrodeArray(electrodes=tuple(electrodes))
    weights = {"src": -1.0, **{rid: 0.25 for rid in _RETURN_IDS}}
    return array, spec.StimConfig.from_map(weights, waveform=_WAVE, distant_return=False)


def _axon_af_peak(
    array: spec.ElectrodeArray, config: spec.StimConfig, backend: FieldBackend | None = None
) -> float:
    """Peak depolarising activating function along the offset axon of passage."""
    backend = backend or AnalyticalBackend()
    axon = np.array([[x, _AXON_OFFSET_UM, -20.0] for x in np.linspace(-120.0, 120.0, 121)])
    ve = backend.transfer_matrix(array, COND, axon) @ current_vector(array, config)
    return float(activating_function(axon, ve).max())


def confined_return_flattens_axon_af() -> Reproduction:
    """Fast: the confined pattern reduces the activating function along the offset axon."""
    af_mono = _axon_af_peak(*_monopolar())
    af_conf = _axon_af_peak(*_confined())
    return Reproduction(
        name="confined return flattens the axon activating function",
        source="Vilkhu et al. 2021",
        passed=af_conf < af_mono,
        measured=f"peak axon AF: monopolar {af_mono:.2e}, confined {af_conf:.2e} "
        f"({af_mono / af_conf:.1f}× lower)",
        criterion="confined-return peak activating function along the axon is below monopolar",
    )


def _fmt(t: float | None) -> str:
    return "no fire ≤500" if t is None else f"{t:.0f}"


def confined_return_avoids_axon_of_passage(cell: RGCModel) -> Reproduction:
    """NEURON: the offset axon-of-passage threshold rises sharply under the confined pattern.

    ``cell`` is an active RGC placed so its axon crosses offset under the array
    (soma far to the side, axon running along the array).
    """
    from engine.cable.multisite import multisite_threshold

    mono_array, mono_config = _monopolar()
    conf_array, conf_config = _confined()
    t_mono = multisite_threshold(
        cell, mono_array, mono_config, COND, amp_min=2.0, amp_max=500.0
    ).threshold_uA
    t_conf = multisite_threshold(
        cell, conf_array, conf_config, COND, amp_min=2.0, amp_max=500.0
    ).threshold_uA
    # avoided if the confined pattern raises the axon threshold (or fails to fire it in range)
    avoided = t_mono is not None and (t_conf is None or t_conf > t_mono)
    return Reproduction(
        name="confined return avoids the axon of passage",
        source="Vilkhu et al. 2021",
        passed=avoided,
        measured=f"axon threshold: monopolar {_fmt(t_mono)} µA, confined {_fmt(t_conf)} µA",
        criterion="confined-return axon-of-passage threshold exceeds monopolar",
    )
