"""Validation — pure functions that turn an invalid spec into clear Problems.

`validate(obj)` checks one spec object in isolation; `validate_scene(...)` adds
the cross-object rules that need more than one object (a config referencing a
missing electrode, layers not spanning the patch depth). Both are pure and
total — same input produces the same list of Problems — so the engine, API,
UI, and tests all surface identical errors. An empty list means valid.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import singledispatch
from typing import Literal

from .conductivity import HomogeneousConductivity, LayeredConductivity
from .conventions import CHARGE_BALANCE_ATOL, GEOMETRY_OVERLAP_ATOL_UM
from .geometry import Electrode, ElectrodeArray
from .patch import RetinalPatch
from .stim import StimConfig, Waveform
from .study import StudyDefinition, Sweep

Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class Problem:
    """A single validation finding. `code` is stable and machine-readable so
    tests and the UI can key on it; `message` is human-facing; `where` locates
    it (an id or a field path)."""

    code: str
    message: str
    severity: Severity = "error"
    where: str = ""


def has_errors(problems: list[Problem]) -> bool:
    """True if any problem is error-severity (warnings alone do not invalidate)."""
    return any(p.severity == "error" for p in problems)


# --- helpers ---------------------------------------------------------------


def _radius_um(e: Electrode) -> float:
    if e.shape == "poly" and e.boundary_um:
        return max(math.dist(e.pos_um, b) for b in e.boundary_um)
    return e.size_um / 2.0


def _electrode_problems(e: Electrode, where: str) -> list[Problem]:
    problems: list[Problem] = []
    if e.size_um < 0:
        problems.append(
            Problem("negative-electrode-size", f"electrode {e.id!r} has negative size", where=where)
        )
    if e.shape == "poly" and not e.boundary_um:
        problems.append(
            Problem(
                "poly-missing-boundary", f"polygon electrode {e.id!r} has no boundary", where=where
            )
        )
    return problems


def _patch_depth_um(patch: RetinalPatch) -> float:
    """Deepest tissue point below the array plane (z = 0), in microns."""
    zs = [c.soma_um[2] for c in patch.cells]
    for c in patch.cells:
        zs.extend(p[2] for p in c.axon_um)
    return max(0.0, -min(zs)) if zs else 0.0


# --- per-object validation (dispatch on type) ------------------------------


@singledispatch
def validate(obj: object) -> list[Problem]:
    raise TypeError(f"no validator registered for {type(obj).__name__}")


@validate.register(Electrode)
def _validate_electrode(e: Electrode) -> list[Problem]:
    return _electrode_problems(e, where=e.id)


@validate.register(ElectrodeArray)
def _validate_array(array: ElectrodeArray) -> list[Problem]:
    if not array.electrodes:
        return [Problem("empty-array", "electrode array has no electrodes")]

    problems: list[Problem] = []
    seen: set[str] = set()
    for e in array.electrodes:
        if e.id in seen:
            problems.append(
                Problem(
                    "duplicate-electrode-id", f"electrode id {e.id!r} is not unique", where=e.id
                )
            )
        seen.add(e.id)
    for i, e in enumerate(array.electrodes):
        problems += _electrode_problems(e, where=f"electrodes[{i}]")

    els = array.electrodes
    for i in range(len(els)):
        for j in range(i + 1, len(els)):
            gap = math.dist(els[i].pos_um, els[j].pos_um) - (
                _radius_um(els[i]) + _radius_um(els[j])
            )
            if gap < -GEOMETRY_OVERLAP_ATOL_UM:
                problems.append(
                    Problem(
                        "electrode-overlap",
                        f"electrodes {els[i].id!r} and {els[j].id!r} overlap",
                        where=f"{els[i].id},{els[j].id}",
                    )
                )
    return problems


@validate.register(Waveform)
def _validate_waveform(wf: Waveform) -> list[Problem]:
    problems: list[Problem] = []
    if wf.phase_width_us <= 0:
        problems.append(
            Problem("waveform-nonpositive-phase", "phase_width_us must be > 0", where="waveform")
        )
    if wf.interphase_gap_us < 0:
        problems.append(
            Problem("waveform-negative-gap", "interphase_gap_us must be >= 0", where="waveform")
        )
    if wf.amplitude_scale_uA == 0:
        problems.append(
            Problem(
                "waveform-zero-amplitude",
                "amplitude_scale_uA is 0 (no current)",
                severity="warning",
                where="waveform",
            )
        )
    return problems


@validate.register(StimConfig)
def _validate_stimconfig(cfg: StimConfig) -> list[Problem]:
    problems: list[Problem] = list(validate(cfg.waveform))
    if not cfg.weights:
        problems.append(
            Problem("empty-config", "configuration has no electrode weights", where="weights")
        )
    ids = [eid for eid, _ in cfg.weights]
    if len(set(ids)) != len(ids):
        problems.append(
            Problem(
                "duplicate-weight-id",
                "an electrode appears more than once in weights",
                where="weights",
            )
        )
    if cfg.weights and not cfg.distant_return:
        total = math.fsum(w for _, w in cfg.weights)
        if abs(total) > CHARGE_BALANCE_ATOL:
            problems.append(
                Problem(
                    "charge-imbalance",
                    f"on-array weights must sum to 0 (got {total:g})",
                    where="weights",
                )
            )
    return problems


@validate.register(HomogeneousConductivity)
def _validate_homogeneous(c: HomogeneousConductivity) -> list[Problem]:
    if c.sigma_S_per_m <= 0:
        return [Problem("nonpositive-conductivity", "sigma_S_per_m must be > 0")]
    return []


@validate.register(LayeredConductivity)
def _validate_layered(c: LayeredConductivity) -> list[Problem]:
    if not c.layers:
        return [Problem("empty-conductivity", "layered conductivity has no layers")]
    problems: list[Problem] = []
    for i, layer in enumerate(c.layers):
        where = f"layers[{i}]"
        if layer.sigma_S_per_m <= 0:
            problems.append(
                Problem("nonpositive-conductivity", "layer sigma_S_per_m must be > 0", where=where)
            )
        if layer.thickness_um <= 0:
            problems.append(
                Problem("nonpositive-thickness", "layer thickness_um must be > 0", where=where)
            )
        if layer.anisotropy is not None and any(a <= 0 for a in layer.anisotropy):
            problems.append(
                Problem("nonpositive-anisotropy", "anisotropy components must be > 0", where=where)
            )
    return problems


@validate.register(RetinalPatch)
def _validate_patch(patch: RetinalPatch) -> list[Problem]:
    problems: list[Problem] = []
    if not patch.cells:
        problems.append(Problem("empty-patch", "patch has no cells"))
    seen: set[str] = set()
    for c in patch.cells:
        if c.id in seen:
            problems.append(
                Problem("duplicate-cell-id", f"cell id {c.id!r} is not unique", where=c.id)
            )
        seen.add(c.id)
    if patch.cells and patch.target_id not in seen:
        problems.append(
            Problem(
                "no-target",
                f"target_id {patch.target_id!r} is not a cell in the patch",
                where="target_id",
            )
        )
    return problems


@validate.register(Sweep)
def _validate_sweep(sw: Sweep) -> list[Problem]:
    problems: list[Problem] = []
    if not sw.path:
        problems.append(Problem("empty-sweep-path", "sweep path is empty", where="path"))
    if not sw.values:
        problems.append(Problem("empty-sweep-values", "sweep has no values", where=sw.path))
    return problems


@validate.register(StudyDefinition)
def _validate_study(study: StudyDefinition) -> list[Problem]:
    problems: list[Problem] = []
    if not study.sweeps:
        problems.append(Problem("empty-study", "study has no sweeps"))
    for sw in study.sweeps:
        problems += validate(sw)
    return problems


# --- cross-object validation -----------------------------------------------


def validate_scene(
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: HomogeneousConductivity | LayeredConductivity,
    patch: RetinalPatch,
) -> list[Problem]:
    """Validate a full simulation scene: each object, plus the rules that only
    make sense across objects."""
    problems: list[Problem] = []
    problems += validate(array)
    problems += validate(config)
    problems += validate(conductivity)
    problems += validate(patch)

    known = set(array.ids())
    for eid, _ in config.weights:
        if eid not in known:
            problems.append(
                Problem(
                    "unknown-electrode",
                    f"configuration references electrode {eid!r} not in the array",
                    where=eid,
                )
            )

    if isinstance(conductivity, LayeredConductivity) and conductivity.layers and patch.cells:
        depth = _patch_depth_um(patch)
        spanned = math.fsum(layer.thickness_um for layer in conductivity.layers)
        if spanned + GEOMETRY_OVERLAP_ATOL_UM < depth:
            problems.append(
                Problem(
                    "layers-do-not-span-depth",
                    f"layers span {spanned:g} um but the patch reaches {depth:g} um deep",
                    where="layers",
                )
            )
    return problems
