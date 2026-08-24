"""Fan 2019: local return sharpens the field, improving selectivity (P3 S1).

A monopolar electrode (distant return) spreads current broadly, so a neighbouring
off-target cell is nearly as excitable as the target. Returning the current
*locally* on a ring of surrounding electrodes turns the monopole into a confined
source whose field falls off far faster with distance: the mechanism Fan et al.
(2019) identify for improved selectivity. We measure it as the field-level
selectivity ``|Ve(target)| / |Ve(off-target)|`` at the somata: bigger means the
target is favoured over the neighbour.

**Scope (honest finding).** The field-sharpening mechanism reproduces *robustly*
(a large gain across geometries). The *full NEURON somatic threshold-ratio* gain
does **not** reproduce in this reduced tier (analytical field + mouse RGC):
activation is AIS/dendrite-dominated, so a tight return ring penalises the
centred target's own AIS while a loose one fails to suppress the off-target. There
is no middle ground, and off-target thresholds even come out non-monotonic with
distance because the dendritic arbor reaches toward the electrode.
Magnitude/threshold validation is therefore deferred to Phase 4 (FEM + primate
morphology); here we reproduce the mechanism at the field level.
"""

from __future__ import annotations

import numpy as np

from engine import spec
from engine.field import AnalyticalBackend, FieldBackend, current_vector

from .reproduction import Reproduction

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
_WAVE = spec.Waveform(phase_width_us=200.0)
_RETURN_IDS = ("ret0", "ret1", "ret2", "ret3")
_TARGET_UM = (0.0, 0.0, -20.0)
_OFF_UM = (60.0, 0.0, -20.0)


def _array(ring_um: float = 35.0) -> spec.ElectrodeArray:
    """Source over the target + a symmetric ring of return electrodes."""
    ring = ((ring_um, 0.0), (-ring_um, 0.0), (0.0, ring_um), (0.0, -ring_um))
    electrodes = [spec.Electrode(id="src", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)]
    electrodes += [
        spec.Electrode(id=rid, pos_um=(x, y, 0.0), shape="disk", size_um=10.0)
        for rid, (x, y) in zip(_RETURN_IDS, ring, strict=True)
    ]
    return spec.ElectrodeArray(electrodes=tuple(electrodes))


def _field_selectivity(
    array: spec.ElectrodeArray, config: spec.StimConfig, backend: FieldBackend | None = None
) -> float:
    """|Ve(target)| / |Ve(off-target)| at the somata; higher favours the target."""
    backend = backend or AnalyticalBackend()
    points = np.array([_TARGET_UM, _OFF_UM], dtype=float)
    ve = backend.transfer_matrix(array, COND, points) @ current_vector(array, config)
    return abs(float(ve[0])) / abs(float(ve[1]))


def local_return_sharpens_the_field() -> Reproduction:
    """Field-level selectivity: local return vs monopolar on one target/off-target pair."""
    array = _array()
    monopolar = spec.StimConfig.from_map({"src": -1.0}, waveform=_WAVE, distant_return=True)
    local_weights = {"src": -1.0, **{rid: 0.25 for rid in _RETURN_IDS}}
    local = spec.StimConfig.from_map(local_weights, waveform=_WAVE, distant_return=False)

    s_mono = _field_selectivity(array, monopolar)
    s_local = _field_selectivity(array, local)
    return Reproduction(
        name="local return sharpens the field (selectivity)",
        source="Fan et al. 2019",
        passed=s_local > s_mono,
        measured=f"soma-Ve selectivity: monopolar {s_mono:.1f}×, local return {s_local:.1f}×",
        criterion="local-return field-selectivity |Ve_target|/|Ve_off| exceeds monopolar",
        note=(
            "Field-sharpening mechanism reproduces robustly. The full-model somatic "
            "threshold-ratio gain is confounded by AIS/dendrite activation in this reduced "
            "tier (analytical + mouse RGC) and is deferred to Phase 4 (FEM + primate morphology)."
        ),
    )
