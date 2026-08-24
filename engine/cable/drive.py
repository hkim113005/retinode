"""Extracellular field drive: the field engine meets the cable engine (S3).

The transfer matrix A (field engine) gives Ve at each compartment per unit
current; ``Ve = A @ I`` is the extracellular potential the electrode array
imposes. We apply it through NEURON's ``extracellular`` mechanism
(``e_extracellular``), stepped through the biphasic waveform in time.

Sign chain (must hold): cathodic current is negative, A is positive, so Ve is
negative under the electrode; NEURON's ``v = v_internal − e_extracellular``, so a
negative e_extracellular depolarizes: a cathodic pulse over the soma fires the
cell, an anodic one does not.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from engine.field import AnalyticalBackend, FieldBackend, current_vector
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .activating import activating_function
from .morphology import RGCModel
from .simulate import SpikeResult


def segment_coords(model: RGCModel) -> tuple[np.ndarray, list]:
    """Center coordinates (µm, m×3) of every segment, with matching segment refs.

    Coordinates interpolate each section's 3D points at the segment centers, so
    they line up with where the field must be sampled and applied.
    """
    ox, oy, oz = getattr(model, "origin_um", (0.0, 0.0, 0.0))  # soma's patch position
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
                    float(np.interp(a, arcs, xs)) + ox,
                    float(np.interp(a, arcs, ys)) + oy,
                    float(np.interp(a, arcs, zs)) + oz,
                )
            )
            segs.append(seg)
    return np.array(coords, dtype=float), segs


def segment_regions(model: RGCModel) -> list[str]:
    """Region label per segment, aligned one-to-one with ``segment_coords`` order.

    Sections with fewer than 2 3D points are skipped identically to
    ``segment_coords``, so the two lists index the same segments.
    """
    labels: list[str] = []
    for region, secs in model.regions().items():
        for sec in secs:
            if sec.n3d() < 2:
                continue
            labels.extend(region for _ in sec)
    return labels


def compute_ve(
    model: RGCModel,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    backend: FieldBackend | None = None,
) -> tuple[np.ndarray, list]:
    """Ve (mV) at every segment for the config, plus the matching segment refs.

    A convenience for one-off single-config drives; it solves the transfer matrix
    and applies the config in one shot. Callers that reuse the field across many
    configs (threshold search, sweeps) should ``solve_field`` once and call
    ``SolvedField.ve`` per config instead.
    """
    from .solved import solve_field  # lazy: keeps drive independent of solved

    solved = solve_field(model, array, conductivity, backend)
    return solved.ve(config), solved.segs


def activating_function_along_axon(
    model: RGCModel,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    backend: FieldBackend | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Ve-based activating function along the axon of passage (hillock→AIS→axon).

    Returns ``(coords, af)`` for the ordered axonal compartments, where ``af`` is the
    Rattay activating function ∂²Ve/∂s² (mV/µm²). Under a cathodic electrode Ve
    dips under the electrode, so ``af`` peaks positive (depolarizing) there. This
    is the geometry-level predictor of where the axon fires, without a NEURON run.
    """
    backend = backend or AnalyticalBackend()
    coords, _ = segment_coords(model)
    ve = backend.transfer_matrix(array, conductivity, coords) @ current_vector(array, config)
    regions = segment_regions(model)
    idx = [i for i, r in enumerate(regions) if r in ("hillock", "ais", "axon")]
    axon_coords = coords[idx]
    return axon_coords, activating_function(axon_coords, ve[idx])


def leading_scale(waveform: Any, monophasic: bool) -> float:
    """The scale applied to Ve on the pulse's *first* phase.

    ``+1`` applies the field as computed: a cathodic leading edge when the driven
    electrode is a cathode (negative weight → negative Ve → depolarizing). Anodic-first
    biphasic (``cathodic_first=False``) leads with ``-Ve`` and recovers with ``+Ve``,
    which is a real, distinct stimulus. A **monophasic** pulse has a single edge, so
    its polarity is the field (weight) sign and ``cathodic_first`` does not apply.
    Honouring it there would just double the weight-sign control.
    """
    return 1.0 if (monophasic or waveform.cathodic_first) else -1.0


def applied_phase_width_us(phase_width_us: float, dt_ms: float = 0.025) -> float:
    """The phase width :func:`apply_field_pulse` will actually deliver.

    Phase timing is quantized to whole integration steps, so a requested width that
    is not a multiple of ``dt_ms`` is rounded to the nearest step. Use this to report
    a threshold against the width that was applied rather than the one asked for.
    """
    return int(round(phase_width_us * 1e-3 / dt_ms)) * dt_ms * 1e3


def apply_field_pulse(
    model: RGCModel,
    ve: np.ndarray,
    segs: list,
    waveform: Any,
    *,
    monophasic: bool = False,
    delay_ms: float = 5.0,
    t_stop_ms: float = 40.0,
    dt_ms: float = 0.025,
    v_init_mV: float = -65.0,
) -> None:
    """Insert ``extracellular`` and drive Ve over the (bi/mono)phasic pulse.

    Caller installs any spike recorders before calling; they populate during the
    run. Ve is the field during phase 1; the second phase applies its reverse.

    **Phase timing is quantized to whole ``dt_ms`` steps**, and both phases are given
    the *same* step count, so the biphasic pulse is charge balanced by construction.
    Advancing each phase to a nominal wall-clock target instead (what this used to do)
    silently broke that: ``h.t`` overshoots phase 1's target by up to one step, and
    phase 2's target is measured from the nominal time, so phase 2 got fewer steps than
    phase 1. At ``phase_width_us=60`` with the default ``dt_ms=0.025`` that delivered
    75 µs cathodic against 50 µs anodic; at 10 µs the interphase gap and the entire
    recovery phase ran zero steps, delivering a monophasic pulse that was reported as
    a balanced biphasic one.

    A phase width below one timestep cannot be delivered at all, so it raises rather
    than rounding up to a full step and misattributing the result to the width asked
    for. ``phase_width_us`` that is not a whole multiple of the timestep is rounded to
    the nearest step; :func:`applied_phase_width_us` reports what was actually applied.
    """
    h = model.h
    for sec in model.all_sections():
        sec.insert("extracellular")
    pw = waveform.phase_width_us * 1e-3  # ms
    gap = waveform.interphase_gap_us * 1e-3

    n_phase = int(round(pw / dt_ms))
    if n_phase < 1:
        raise ValueError(
            f"phase_width_us={waveform.phase_width_us:g} is shorter than one "
            f"integration step (dt_ms={dt_ms:g} = {dt_ms * 1e3:g} µs), so no drive "
            "would be delivered. Raise the phase width or lower dt_ms."
        )
    n_gap = int(round(gap / dt_ms))
    if gap > 0.0 and n_gap < 1:
        raise ValueError(
            f"interphase_gap_us={waveform.interphase_gap_us:g} rounds to zero "
            f"integration steps (dt_ms={dt_ms:g}); it would be silently dropped."
        )

    def set_field(scale: float) -> None:
        for seg, value in zip(segs, ve, strict=True):
            seg.e_extracellular = value * scale

    def advance_to(t_target: float) -> None:
        while h.t < t_target - 1e-9:
            h.fadvance()

    def advance_steps(n: int) -> None:
        for _ in range(n):
            h.fadvance()

    lead = leading_scale(waveform, monophasic)  # +1 cathodic-first, -1 anodic-first
    h.dt = dt_ms
    h.finitialize(v_init_mV)
    set_field(0.0)
    advance_to(delay_ms)
    set_field(lead)  # phase 1: the imposed field Ve (reversed if anodic-first)
    advance_steps(n_phase)
    if not monophasic:
        set_field(0.0)  # interphase gap
        advance_steps(n_gap)
        set_field(-lead)  # phase 2: charge recovery (reversed relative to phase 1)
        advance_steps(n_phase)  # same count as phase 1 => balanced by construction
    set_field(0.0)
    advance_to(t_stop_ms)


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

    ``monophasic=True`` applies only the first phase (the field Ve), which is useful
    for isolating the sign chain, since a biphasic pulse's reversed second phase can
    itself excite. Default is the full biphasic (physical) pulse.
    """
    ve, segs = compute_ve(model, array, config, conductivity, backend)
    h = model.h

    spikes = h.Vector()
    detector = h.NetCon(model.soma_sec(0.5)._ref_v, None, sec=model.soma_sec)
    detector.threshold = threshold_mV
    detector.record(spikes)
    v_soma = h.Vector()
    v_soma.record(model.soma_sec(0.5)._ref_v)

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

    return SpikeResult(
        n_spikes=int(spikes.size()),
        times_ms=tuple(spikes),
        v_peak_mV=float(v_soma.max()),
        v_min_mV=float(v_soma.min()),
    )
