"""Single-cell threshold reproductions vs the literature (S5, Wk-4 checkpoint).

Robust, density-independent checks — trends, ratios, initiation site, and range
— not absolute-value matching (our densities are nominal; the real biophysical
test is the Phase-3 ex-vivo primate reproductions). Search granularity is coarse
here: we need trends, not high precision, and CI runtime is bounded.
"""

from __future__ import annotations

from engine import spec
from engine.cable.initiation import initiation_site
from engine.cable.morphology import RGCModel
from engine.cable.threshold import extracellular_threshold

from .reproduction import Reproduction

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
_LADDER = 1.6  # coarse: trends need no precision, keeps NEURON runs down
_RTOL = 0.06


def _electrode(cell: RGCModel, dx: float = 0.0, height_um: float = 40.0) -> spec.ElectrodeArray:
    cx, cy, cz = cell._soma_center_um()
    return spec.ElectrodeArray(
        electrodes=(
            spec.Electrode(
                id="e", pos_um=(cx + dx, cy, cz + height_um), shape="disk", size_um=10.0
            ),
        )
    )


def _threshold(
    cell: RGCModel, dx: float = 0.0, height_um: float = 40.0, pw: float = 200.0
) -> float | None:
    config = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=pw), distant_return=True
    )
    return extracellular_threshold(
        cell,
        _electrode(cell, dx, height_um),
        config,
        COND,
        amp_min=2.0,
        amp_max=400.0,
        ladder=_LADDER,
        rel_tol=_RTOL,
    ).threshold_uA


def _fmt(t: float | None) -> str:
    return f"{t:.0f}" if t is not None else "n/a"


def threshold_rises_with_distance(cell: RGCModel) -> Reproduction:
    ts = [_threshold(cell, height_um=h) for h in (25.0, 40.0, 60.0)]
    vals = [t for t in ts if t is not None]
    passed = len(vals) == len(ts) and all(vals[i] < vals[i + 1] for i in range(len(vals) - 1))
    return Reproduction(
        name="threshold rises with electrode distance",
        source="Greenberg 1999",
        passed=passed,
        measured=f"{'/'.join(_fmt(t) for t in ts)} uA at 25/40/60 um",
        criterion="monotonic increase with electrode-cell distance",
    )


def axon_of_passage_is_excitable(cell: RGCModel) -> Reproduction:
    t_soma = _threshold(cell, dx=0.0)
    t_axon = _threshold(cell, dx=200.0)  # over the distal axon (runs +x)
    if t_soma is None or t_axon is None:
        passed, ratio = False, "n/a"
    else:
        passed = t_axon <= t_soma and 1.0 < t_axon < 150.0
        ratio = f"{t_soma / t_axon:.2f}"
    return Reproduction(
        name="axon of passage is highly excitable",
        source="Vilkhu 2021 / sodium-band literature",
        passed=passed,
        measured=f"axon={_fmt(t_axon)} vs soma={_fmt(t_soma)} uA (soma/axon {ratio})",
        criterion="axon threshold <= soma threshold, in physiological range",
        note=(
            "Diverges from Greenberg 1999's original soma<axon claim; consistent with a proper "
            "Na band and the axon-avoidance premise — axons are the low-threshold off-target."
        ),
    )


def spike_initiates_at_sodium_band(cell: RGCModel) -> Reproduction:
    thr = _threshold(cell, dx=0.0)
    if thr is None:
        return Reproduction(
            name="spike initiates at the sodium-channel band (AIS)",
            source="Jeng/Fried; modern refinement of Greenberg 1999",
            passed=False,
            measured="no threshold found",
            criterion="spike initiates in the AIS/proximal-axon region, near threshold",
        )
    config = spec.StimConfig.from_map(
        {"e": -1.0},
        waveform=spec.Waveform(phase_width_us=200.0, amplitude_scale_uA=thr * 1.02),
        distant_return=True,
    )
    result = initiation_site(cell, _electrode(cell), config, COND, dt_ms=0.005)
    return Reproduction(
        name="spike initiates at the sodium-channel band (AIS)",
        source="Jeng/Fried; modern refinement of Greenberg 1999",
        passed=result.initiation_region in ("ais", "hillock"),
        measured=f"initiation region = {result.initiation_region}",
        criterion="spike initiates in the AIS/proximal-axon region (not soma), near threshold",
    )


def strength_duration_decreases(cell: RGCModel) -> Reproduction:
    pws = (50.0, 100.0, 200.0, 400.0)
    ts = [_threshold(cell, pw=pw) for pw in pws]
    vals = [t for t in ts if t is not None]
    passed = len(vals) == len(ts) and all(vals[i] > vals[i + 1] for i in range(len(vals) - 1))
    return Reproduction(
        name="strength-duration: threshold falls with pulse width",
        source="Greenberg 1999",
        passed=passed,
        measured=f"{'/'.join(_fmt(t) for t in ts)} uA at 50/100/200/400 us",
        criterion="threshold decreases monotonically with pulse width (<0.5 ms, direct activation)",
    )


def thresholds_in_physiological_range(cell: RGCModel) -> Reproduction:
    t = _threshold(cell, dx=0.0, pw=200.0)
    passed = t is not None and 1.0 < t < 150.0
    return Reproduction(
        name="thresholds in physiological range",
        source="Tsai 2012 / Greenberg 1999",
        passed=passed,
        measured=f"{_fmt(t)} uA (soma, 40 um, 200 us)",
        criterion="1-150 uA, plausible for epiretinal stimulation",
    )


def all_reproductions(cell: RGCModel) -> list[Reproduction]:
    return [
        threshold_rises_with_distance(cell),
        axon_of_passage_is_excitable(cell),
        spike_initiates_at_sodium_band(cell),
        strength_duration_decreases(cell),
        thresholds_in_physiological_range(cell),
    ]
