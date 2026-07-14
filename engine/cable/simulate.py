"""Drive a single RGC with injected current and detect spikes (S2d sanity).

Intracellular current injection (IClamp) at the soma — the basic check that the
assembled cell fires action potentials correctly. Extracellular *field* drive is
S3. Spike detection is at the soma for now; multi-site detection (a spike at any
compartment) is S6. Integration is fixed-step (the FM mod is CVODE-incompatible).
"""

from __future__ import annotations

from dataclasses import dataclass

from .morphology import RGCModel


@dataclass(frozen=True)
class SpikeResult:
    n_spikes: int
    times_ms: tuple[float, ...]
    v_peak_mV: float


def run_current_step(
    model: RGCModel,
    amp_nA: float,
    *,
    delay_ms: float = 5.0,
    dur_ms: float = 50.0,
    t_stop_ms: float = 60.0,
    dt_ms: float = 0.025,
    v_init_mV: float = -65.0,
    threshold_mV: float = -10.0,
) -> SpikeResult:
    """Inject a somatic current step and return the soma spike count/times/peak."""
    h = model.h
    clamp = h.IClamp(model.soma_sec(0.5))
    clamp.delay, clamp.dur, clamp.amp = delay_ms, dur_ms, amp_nA

    spikes = h.Vector()
    detector = h.NetCon(model.soma_sec(0.5)._ref_v, None, sec=model.soma_sec)
    detector.threshold = threshold_mV
    detector.record(spikes)

    v_soma = h.Vector()
    v_soma.record(model.soma_sec(0.5)._ref_v)

    h.dt = dt_ms
    h.finitialize(v_init_mV)
    for _ in range(int(t_stop_ms / dt_ms)):
        h.fadvance()

    return SpikeResult(
        n_spikes=int(spikes.size()),
        times_ms=tuple(spikes),
        v_peak_mV=float(v_soma.max()),
    )
