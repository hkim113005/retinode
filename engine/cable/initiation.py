"""Where does the spike start? Detect the earliest-firing region (S5/R3).

Records spike times at a representative segment of each region and returns the
region that crossed threshold first. Under extracellular stimulation the spike
should initiate at the sodium-channel band (AIS), not the soma. That is the
modern understanding (vs Greenberg 1999's soma prediction) and the reason we
model an elevated Na band. A focused precursor to multi-site detection (S6b).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.field import FieldBackend
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .drive import apply_field_pulse, compute_ve
from .morphology import RGCModel


@dataclass(frozen=True)
class InitiationResult:
    initiation_region: str | None  # region that spiked first (None if no spike)
    first_spike_ms: float | None
    per_region_first_ms: dict[str, float]  # earliest spike time per region


def initiation_site(
    model: RGCModel,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    backend: FieldBackend | None = None,
    monophasic: bool = True,
    delay_ms: float = 5.0,
    t_stop_ms: float = 40.0,
    dt_ms: float = 0.025,
    v_init_mV: float = -65.0,
    threshold_mV: float = -10.0,
) -> InitiationResult:
    """Drive the cell and report which region's representative segment fires first."""
    ve, segs = compute_ve(model, array, config, conductivity, backend)
    h = model.h

    recorders: dict[str, Any] = {}
    detectors = []
    for region, secs in model.regions().items():
        if not secs:
            continue
        sec = secs[len(secs) // 2]
        vec = h.Vector()
        nc = h.NetCon(sec(0.5)._ref_v, None, sec=sec)
        nc.threshold = threshold_mV
        nc.record(vec)
        recorders[region] = vec
        detectors.append(nc)  # keep alive

    apply_field_pulse(
        model,
        ve,
        segs,
        config.waveform,
        monophasic=monophasic,
        delay_ms=delay_ms,
        t_stop_ms=t_stop_ms,
        dt_ms=dt_ms,
        v_init_mV=v_init_mV,
    )

    per_region = {r: float(v[0]) for r, v in recorders.items() if v.size() > 0}
    if not per_region:
        return InitiationResult(None, None, {})
    first_region = min(per_region, key=lambda r: per_region[r])
    return InitiationResult(first_region, per_region[first_region], per_region)
