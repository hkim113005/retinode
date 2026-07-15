"""Where does the spike start? Detect the earliest-firing region (S5/R3).

Records spike times at a representative segment of each region and returns the
region that crossed threshold first. Under extracellular stimulation the spike
should initiate at the sodium-channel band (AIS), not the soma — the modern
understanding (vs Greenberg 1999's soma prediction) and the reason we model an
elevated Na band. A focused precursor to the full multi-site detection in S6.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.field import AnalyticalBackend, FieldBackend, current_vector
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .drive import segment_coords
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
    backend = backend or AnalyticalBackend()
    coords, segs = segment_coords(model)
    ve = backend.transfer_matrix(array, conductivity, coords) @ current_vector(array, config)

    h = model.h
    for sec in model.all_sections():
        sec.insert("extracellular")

    # one spike-time recorder per region (at a representative mid-segment)
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

    wf = config.waveform
    pw = wf.phase_width_us * 1e-3
    gap = wf.interphase_gap_us * 1e-3

    def set_field(scale: float) -> None:
        for seg, value in zip(segs, ve, strict=True):
            seg.e_extracellular = value * scale

    def advance_to(t: float) -> None:
        while h.t < t - 1e-9:
            h.fadvance()

    h.dt = dt_ms
    h.finitialize(v_init_mV)
    set_field(0.0)
    advance_to(delay_ms)
    set_field(1.0)
    advance_to(delay_ms + pw)
    if not monophasic:
        set_field(0.0)
        advance_to(delay_ms + pw + gap)
        set_field(-1.0)
        advance_to(delay_ms + pw + gap + pw)
    set_field(0.0)
    advance_to(t_stop_ms)

    per_region = {r: float(v[0]) for r, v in recorders.items() if v.size() > 0}
    if not per_region:
        return InitiationResult(None, None, {})
    first_region = min(per_region, key=lambda r: per_region[r])
    return InitiationResult(first_region, per_region[first_region], per_region)
