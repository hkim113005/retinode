"""Axon-trajectory distribution: threshold spread over K perturbed paths (S6d).

An epiretinal threshold depends strongly on the *ascending axon* — how the axon of
passage runs relative to the electrode — but the true 3D path of any one cell's
axon is uncertain. So instead of trusting a single guessed trajectory we sample K
of them (the nominal direction rotated by small angular jitters about the array
normal) and report the threshold spread. That spread is the honest error bar on a
per-cell threshold.

Small K here by design: this is the machinery and its sanity check. Full
trajectory × population sweeps (every cell × K paths) are deliberately a Phase-5
concern — see population.py. The direction sampling is deterministic (evenly
spaced angles, no RNG) so a spread is reproducible.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from engine.field import FieldBackend
from engine.spec import RGC, ConductivityModel, ElectrodeArray, StimConfig

from .channels import ChannelConfig, ChannelDensities, build_active_rgc
from .multisite import multisite_threshold
from .placement import axon_direction

Vec3 = tuple[float, float, float]


def perturbed_directions(nominal: Vec3, k: int, jitter_deg: float) -> list[Vec3]:
    """K unit-ish directions: ``nominal`` rotated about +z by evenly spaced angles.

    For k=1 the angle set is {0}; for k≥2 it spans [-jitter, +jitter] inclusive, so
    the nominal path is always among the samples when k is odd. Rotation is about
    the array normal (+z), which reorients the in-plane axon run while keeping its
    depth — the degree of freedom that actually moves an axon across an electrode.
    """
    if k < 1:
        raise ValueError("k must be >= 1")
    dx, dy, dz = nominal
    if k == 1:
        angles = [0.0]
    else:
        step = 2.0 * jitter_deg / (k - 1)
        angles = [-jitter_deg + i * step for i in range(k)]
    out: list[Vec3] = []
    for deg in angles:
        t = math.radians(deg)
        c, s = math.cos(t), math.sin(t)
        out.append((dx * c - dy * s, dx * s + dy * c, dz))
    return out


@dataclass(frozen=True)
class TrajectorySpread:
    thresholds_uA: tuple[float, ...]  # one per sampled trajectory that fired
    directions: tuple[Vec3, ...]  # the sampled axon directions (all k)
    mean_uA: float | None
    std_uA: float | None
    cv: float | None  # coefficient of variation std/mean — the dimensionless spread

    @property
    def n(self) -> int:
        return len(self.thresholds_uA)


def trajectory_spread(
    rgc: RGC,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    optic_disc: Vec3 | None = None,
    k: int = 3,
    jitter_deg: float = 15.0,
    densities: ChannelDensities | None = None,
    channel_config: ChannelConfig | None = None,
    backend: FieldBackend | None = None,
    amp_min: float = 1.0,
    amp_max: float = 500.0,
    ladder: float = 1.5,
    rel_tol: float = 0.04,
) -> TrajectorySpread:
    """Multi-site threshold across K perturbed axon trajectories for one cell."""
    nominal = axon_direction(rgc, optic_disc)
    directions = perturbed_directions(nominal, k, jitter_deg)

    thresholds: list[float] = []
    for d in directions:
        cell = build_active_rgc(
            rgc.cell_type,
            densities=densities,
            config=channel_config,
            origin_um=rgc.soma_um,
            axon_direction=d,
        )
        thr = multisite_threshold(
            cell,
            array,
            config,
            conductivity,
            backend=backend,
            amp_min=amp_min,
            amp_max=amp_max,
            ladder=ladder,
            rel_tol=rel_tol,
        ).threshold_uA
        if thr is not None:
            thresholds.append(thr)

    if not thresholds:
        return TrajectorySpread((), tuple(directions), None, None, None)
    arr = np.array(thresholds, dtype=float)
    mean = float(arr.mean())
    std = float(arr.std())  # population std over the sampled paths
    cv = std / mean if mean > 0 else None
    return TrajectorySpread(tuple(thresholds), tuple(directions), mean, std, cv)
