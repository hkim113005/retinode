"""Extracellular field drive: the field engine meets the cable engine (S3).

The transfer matrix A (field engine) gives Ve at each compartment per unit
current; ``Ve = A @ I`` is the extracellular potential the electrode array
imposes. We apply it through NEURON's ``extracellular`` mechanism
(``e_extracellular``), stepped through the biphasic waveform in time.

Sign chain (must hold): cathodic current is negative, A is positive, so Ve is
negative under the electrode; NEURON's ``v = v_internal − e_extracellular``, so a
negative e_extracellular depolarizes — a cathodic pulse over the soma fires the
cell, an anodic one does not.
"""

from __future__ import annotations

import numpy as np

from engine.field import AnalyticalBackend, FieldBackend, current_vector
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .morphology import RGCModel
from .simulate import SpikeResult


def segment_coords(model: RGCModel) -> tuple[np.ndarray, list]:
    """Center coordinates (µm, m×3) of every segment, with matching segment refs.

    Coordinates interpolate each section's 3D points at the segment centers, so
    they line up with where the field must be sampled and applied.
    """
    coords: list[tuple[float, float, float]] = []
    segs: list = []
    for sec in model.all_sections():
        n3d = sec.n3d()
        if n3d < 2:
            continue
        arcs = np.array([sec.arc3d(i) for i in range(n3d)])
        xs = np.array([sec.x3d(i) for i in range(n3d)])
        ys = np.array([sec.y3d(i) for i in range(n3d)])
        zs = np.array([sec.z3d(i) for i in range(n3d)])
        total = arcs[-1] if arcs[-1] > 0 else 1.0
        for seg in sec:
            a = seg.x * total
            coords.append(
                (
                    float(np.interp(a, arcs, xs)),
                    float(np.interp(a, arcs, ys)),
                    float(np.interp(a, arcs, zs)),
                )
            )
            segs.append(seg)
    return np.array(coords, dtype=float), segs


def run_extracellular_pulse(
    model: RGCModel,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    backend: FieldBackend | None = None,
    monophasic: bool = False,
    delay_ms: float = 5.0,
    t_stop_ms: float = 40.0,
    dt_ms: float = 0.025,
    v_init_mV: float = -65.0,
    threshold_mV: float = -10.0,
) -> SpikeResult:
    """Drive the cell with the array's extracellular field over one pulse.

    ``monophasic=True`` applies only the first phase (the field Ve) — useful for
    isolating the sign chain, since a biphasic pulse's reversed second phase can
    itself excite. Default is the full biphasic (physical) pulse.
    """
    backend = backend or AnalyticalBackend()
    coords, segs = segment_coords(model)
    a = backend.transfer_matrix(array, conductivity, coords)  # (m, n) mV/µA
    ve = a @ current_vector(array, config)  # (m,) mV — the imposed field

    h = model.h
    for sec in model.all_sections():
        sec.insert("extracellular")

    spikes = h.Vector()
    detector = h.NetCon(model.soma_sec(0.5)._ref_v, None, sec=model.soma_sec)
    detector.threshold = threshold_mV
    detector.record(spikes)
    v_soma = h.Vector()
    v_soma.record(model.soma_sec(0.5)._ref_v)

    wf = config.waveform
    pw = wf.phase_width_us * 1e-3  # ms
    gap = wf.interphase_gap_us * 1e-3

    def set_field(scale: float) -> None:
        for seg, value in zip(segs, ve, strict=True):
            seg.e_extracellular = value * scale

    def advance_to(t_target: float) -> None:
        while h.t < t_target - 1e-9:
            h.fadvance()

    h.dt = dt_ms
    h.finitialize(v_init_mV)
    set_field(0.0)
    advance_to(delay_ms)
    set_field(1.0)  # phase 1: the imposed field Ve
    advance_to(delay_ms + pw)
    if not monophasic:
        set_field(0.0)  # interphase gap
        advance_to(delay_ms + pw + gap)
        set_field(-1.0)  # phase 2: charge recovery (reversed)
        advance_to(delay_ms + pw + gap + pw)
    set_field(0.0)
    advance_to(t_stop_ms)

    return SpikeResult(
        n_spikes=int(spikes.size()),
        times_ms=tuple(spikes),
        v_peak_mV=float(v_soma.max()),
        v_min_mV=float(v_soma.min()),
    )
