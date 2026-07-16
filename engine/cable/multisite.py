"""Multi-site activation: a spike at ANY compartment counts (S6b).

The cell is activated if *any* compartment fires — this is why multi-electrode
currents combine nonlinearly (two subthreshold electrodes can each depolarize a
different region and jointly cross threshold somewhere; Vilkhu 2025) and why an
axon of passage is a first-class off-target. A NetCon on every segment records
spike times; the earliest-firing segment is the initiation site.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

from engine.field import FieldBackend
from engine.spec import ConductivityModel, ElectrodeArray, StimConfig

from .drive import apply_field_pulse, segment_regions
from .morphology import RGCModel
from .solved import SolvedField, solve_field
from .threshold import ThresholdResult, find_threshold

__all__ = ["MultisiteResult", "multisite_threshold", "run_multisite", "segment_regions"]


@dataclass(frozen=True)
class MultisiteResult:
    activated: bool  # any compartment fired
    n_active_segments: int
    initiation_region: str | None  # region of the earliest-firing segment
    first_spike_ms: float | None


def run_multisite(
    model: RGCModel,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    solved: SolvedField | None = None,
    backend: FieldBackend | None = None,
    monophasic: bool = True,
    delay_ms: float = 5.0,
    t_stop_ms: float = 40.0,
    dt_ms: float = 0.025,
    v_init_mV: float = -65.0,
    threshold_mV: float = -10.0,
    deactivated: frozenset[int] = frozenset(),
) -> MultisiteResult:
    """Drive the field and detect a spike at any compartment.

    Pass ``solved`` (a pre-solved field for this cell + array + medium) to reuse
    the transfer matrix instead of re-solving it — the caller does this to sweep
    configs or amplitudes cheaply. Without it, the field is solved for this call.

    ``deactivated`` are segment indices severed by the ``displace`` overlap policy
    (they lie inside an electrode body): no detector is placed on them, so a spike
    there cannot count as activation — the cell is scored on its surviving
    compartments. A caller passing ``solved`` must have built it with the same
    ``deactivated`` set (so ``Ve`` is zero there); without ``solved`` we solve it
    here consistently.
    """
    if solved is None:
        solved = solve_field(model, array, conductivity, backend, deactivated=deactivated)
    ve = solved.ve(config)
    segs = solved.segs
    regions = segment_regions(model)
    h = model.h

    vecs: list = []
    detectors = []
    for i, seg in enumerate(segs):
        if i in deactivated:  # severed: inside the metal, not a live compartment
            vecs.append(None)
            continue
        vec = h.Vector()
        nc = h.NetCon(seg._ref_v, None, sec=seg.sec)
        nc.threshold = threshold_mV
        nc.record(vec)
        vecs.append(vec)
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

    first_t: float | None = None
    first_idx: int | None = None
    n_active = 0
    for i, vec in enumerate(vecs):
        if vec is None:  # severed compartment — never monitored
            continue
        if vec.size() > 0:
            n_active += 1
            t0 = float(vec[0])
            if first_t is None or t0 < first_t:
                first_t, first_idx = t0, i

    init_region = regions[first_idx] if first_idx is not None else None
    return MultisiteResult(n_active > 0, n_active, init_region, first_t)


def multisite_threshold(
    model: RGCModel,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    solved: SolvedField | None = None,
    backend: FieldBackend | None = None,
    monophasic: bool = True,
    amp_min: float = 1.0,
    amp_max: float = 500.0,
    ladder: float = 1.5,
    rel_tol: float = 0.03,
    deactivated: frozenset[int] = frozenset(),
) -> ThresholdResult:
    """Threshold (µA) using multi-site activation — a spike anywhere counts.

    The transfer matrix is solved **once** (or taken from ``solved``) and reused
    across every amplitude the search probes — the field is fixed; only the
    current scale changes. Pass ``solved`` to also reuse it across configurations.

    ``deactivated`` (the ``displace`` policy's severed segments) is applied to both
    the field solve and spike detection; a caller-supplied ``solved`` must already
    encode the same set.
    """
    if solved is None:
        solved = solve_field(model, array, conductivity, backend, deactivated=deactivated)

    def activates(amp: float) -> bool:
        wf = dataclasses.replace(config.waveform, amplitude_scale_uA=amp)
        scaled = dataclasses.replace(config, waveform=wf)
        return run_multisite(
            model, array, scaled, conductivity, solved=solved, deactivated=deactivated
        ).activated

    return find_threshold(
        activates, amp_min=amp_min, amp_max=amp_max, ladder=ladder, rel_tol=rel_tol
    )
