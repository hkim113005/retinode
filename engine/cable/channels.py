"""Insert the FM (Fohlmeister-Miller) channels into an RGC, per region.

Conductance densities differ by compartment class — the spike initiates at the
**sodium-channel band (AIS)**, so its gNa is elevated relative to soma, axon, and
(low) dendrites. Temperature is set to 37 C with the FM-2010 q10 scaling of the
gating kinetics (added to spike.mod). Densities here are nominal, FM-2010-informed
starting values; they are calibrated against Greenberg 1999 / Tsai 2012 in S5.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .morphology import RGCModel


@dataclass(frozen=True)
class ChannelDensities:
    """Maximal conductances (S/cm^2 == mho/cm^2). gNa is region-specific.

    These are mammalian (37 C) densities — ~4x the salamander FM defaults. At body
    temperature the faster kinetics shorten the Na open-window, so more channels
    are needed to reach threshold and to repolarize for repetitive firing (the
    FM-2010 mammalian regime; warm neurons carry more channels). Nominal starting
    values — calibrated against Greenberg 1999 / Tsai 2012 in S5.
    """

    gna_soma: float = 0.28
    gna_hillock: float = 0.40
    gna_ais: float = 1.40  # elevated sodium-channel band — spike initiation
    gna_axon: float = 0.28
    gna_dendrite: float = 0.04  # low
    gk: float = 0.048  # delayed rectifier
    ga: float = 0.144  # A-type K
    gca: float = 0.0015  # Ca
    gkc: float = 0.00005  # Ca-activated K


@dataclass(frozen=True)
class ChannelConfig:
    celsius: float = 37.0  # mammalian
    q10: float = 2.5
    ena_mV: float = 35.0
    ek_mV: float = -75.0
    ra_ohm_cm: float = 110.0
    cm_uF_cm2: float = 1.0


def _gna_by_region(d: ChannelDensities) -> dict[str, float]:
    return {
        "soma": d.gna_soma,
        "hillock": d.gna_hillock,
        "ais": d.gna_ais,
        "axon": d.gna_axon,
        "dendrite": d.gna_dendrite,
    }


def _dlambda_nseg(
    sec: Any, ra: float, cm: float, freq: float = 100.0, d_lambda: float = 0.1
) -> int:
    """Odd nseg by the d-lambda rule, so compartments are electrically short."""
    lam = 1.0e5 * math.sqrt(sec.diam / (4.0 * math.pi * freq * ra * cm))
    return int((sec.L / (d_lambda * lam) + 0.9) / 2.0) * 2 + 1


def insert_channels(
    model: RGCModel,
    densities: ChannelDensities | None = None,
    config: ChannelConfig | None = None,
) -> None:
    """Insert FM channels + Ca pump into every region with per-region densities."""
    d = densities or ChannelDensities()
    c = config or ChannelConfig()
    h = model.h
    h.celsius = c.celsius
    h.q10_spike = c.q10

    gna = _gna_by_region(d)
    for region, secs in model.regions().items():
        for sec in secs:
            sec.Ra = c.ra_ohm_cm
            sec.cm = c.cm_uF_cm2
            sec.nseg = _dlambda_nseg(sec, c.ra_ohm_cm, c.cm_uF_cm2)
            sec.insert("spike")  # FM five channels
            sec.insert("cad")  # submembrane calcium pump (feeds Ca-activated K)
            sec.ena = c.ena_mV
            sec.ek = c.ek_mV
            for seg in sec:
                seg.spike.gnabar = gna[region]
                seg.spike.gkbar = d.gk
                seg.spike.gabar = d.ga
                seg.spike.gcabar = d.gca
                seg.spike.gkcbar = d.gkc


def build_active_rgc(
    cell_type: str = "default",
    densities: ChannelDensities | None = None,
    config: ChannelConfig | None = None,
    *,
    origin_um: tuple[float, float, float] = (0.0, 0.0, 0.0),
    axon_direction: tuple[float, float, float] = (1.0, 0.0, 0.0),
) -> RGCModel:
    """Build the morphology and insert channels — a ready-to-simulate RGC."""
    from .morphology import build_rgc

    model = build_rgc(cell_type, origin_um=origin_um, axon_direction=axon_direction)
    insert_channels(model, densities=densities, config=config)
    return model
