"""Charge and safety: pure arithmetic, no NEURON.

For each active electrode we compute charge per phase ``Q = |I|*PW`` and charge
density ``D = Q/A``, then judge safety two ways (the config is unsafe if either
fails, and unsafe configs are excluded from any candidate shortlist):

- **Shannon criterion** (Shannon 1992; McCreery 1990): ``log10(D) = k - log10(Q)``
  is the injury boundary, so a point exceeds it when ``log10(D)+log10(Q) > k``.
  ``k <= 1.5`` is conservative.
- **Material limit**: the electrode material's own charge-injection limit on D.

Units are pinned: current uA, phase width us, so Q in uC = |I|*PW*1e-6; areas in
um^2 converted to cm^2 (1 um^2 = 1e-8 cm^2); D in uC/cm^2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from engine.spec import Electrode, ElectrodeArray, StimConfig

_UM2_PER_CM2 = 1.0e8  # 1 cm^2 = 1e8 um^2


@dataclass(frozen=True)
class SafetyLimits:
    shannon_k: float = 1.5
    # Material charge-injection limit on density (uC/cm^2); None skips the check.
    material_charge_density_uC_per_cm2: float | None = None


DEFAULT_SAFETY_LIMITS = SafetyLimits()


@dataclass(frozen=True)
class ElectrodeSafety:
    electrode_id: str
    charge_per_phase_uC: float
    charge_density_uC_per_cm2: float
    shannon_k: float
    exceeds_shannon: bool
    exceeds_material: bool

    @property
    def safe(self) -> bool:
        return not (self.exceeds_shannon or self.exceeds_material)


@dataclass(frozen=True)
class SafetyReport:
    per_electrode: tuple[ElectrodeSafety, ...]

    @property
    def safe(self) -> bool:
        return all(e.safe for e in self.per_electrode)


def _polygon_area_um2(boundary_um: tuple[tuple[float, float, float], ...]) -> float:
    pts = [(p[0], p[1]) for p in boundary_um]
    n = len(pts)
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def electrode_area_um2(e: Electrode) -> float:
    """Geometric area of the electrode face, in square microns."""
    if e.shape == "disk":
        return math.pi * (e.size_um / 2.0) ** 2
    if e.shape == "square":
        return e.size_um**2
    if e.shape == "hex":  # size is flat-to-flat width
        return (math.sqrt(3.0) / 2.0) * e.size_um**2
    # poly
    return _polygon_area_um2(e.boundary_um) if e.boundary_um else 0.0


def charge_per_phase_uC(current_uA: float, phase_width_us: float) -> float:
    """|I|*PW, with uA*us -> uC (factor 1e-6)."""
    return abs(current_uA) * phase_width_us * 1.0e-6


def assess_safety(
    array: ElectrodeArray,
    config: StimConfig,
    limits: SafetyLimits = DEFAULT_SAFETY_LIMITS,
) -> SafetyReport:
    """Per-active-electrode charge/density and safety verdicts for a config."""
    pw = config.waveform.phase_width_us
    amp = config.waveform.amplitude_scale_uA
    weights = config.weight_map()

    findings: list[ElectrodeSafety] = []
    for e in array.electrodes:
        current = weights.get(e.id, 0.0) * amp
        if current == 0.0:
            continue  # inactive electrode carries no charge
        q = charge_per_phase_uC(current, pw)
        area_cm2 = electrode_area_um2(e) / _UM2_PER_CM2
        d = q / area_cm2 if area_cm2 > 0.0 else math.inf
        # Shannon k for this (D, Q); exceeds the boundary when k > limit.
        k = math.log10(d) + math.log10(q) if (d > 0.0 and q > 0.0) else -math.inf
        exceeds_material = (
            limits.material_charge_density_uC_per_cm2 is not None
            and d > limits.material_charge_density_uC_per_cm2
        )
        findings.append(
            ElectrodeSafety(
                electrode_id=e.id,
                charge_per_phase_uC=q,
                charge_density_uC_per_cm2=d,
                shannon_k=k,
                exceeds_shannon=k > limits.shannon_k,
                exceeds_material=exceeds_material,
            )
        )
    return SafetyReport(per_electrode=tuple(findings))
