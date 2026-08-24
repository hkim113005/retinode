"""Validation: pure functions that turn an invalid spec into clear Problems.

`validate(obj)` checks one spec object in isolation; `validate_scene(...)` adds
the cross-object rules that need more than one object (a config referencing a
missing electrode, layers not spanning the patch depth). Both are pure and
total (the same input always produces the same list of Problems), so the engine,
API, UI, and tests all surface identical errors. An empty list means valid.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from functools import singledispatch
from typing import Literal

from .body import CadBody, Cylinder, Frustum, Hemisphere
from .conductivity import HomogeneousConductivity, LayeredConductivity
from .conventions import CHARGE_BALANCE_ATOL, GEOMETRY_OVERLAP_ATOL_UM
from .geometry import Electrode, ElectrodeArray, radius_um
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


def _all_finite(values: Iterable[float]) -> bool:
    return all(math.isfinite(v) for v in values)


def _body_dims(body: object) -> tuple[tuple[str, float, bool], ...]:
    """``(name, value, must_be_strictly_positive)`` for a body's dimensions.

    ``>= 0`` entries are deliberate: a frustum's ``top_radius_um`` of 0 is a real
    penetrating needle tip, and a CAD body's tip/sides areas default to 0.0 for
    solids loaded before P6 S8, so requiring ``> 0`` would invalidate existing specs.
    """
    if isinstance(body, Hemisphere):
        return (("radius_um", body.radius_um, True),)
    if isinstance(body, Cylinder):
        return (("radius_um", body.radius_um, True), ("height_um", body.height_um, True))
    if isinstance(body, Frustum):
        return (
            ("base_radius_um", body.base_radius_um, True),
            ("top_radius_um", body.top_radius_um, False),
            ("height_um", body.height_um, True),
        )
    if isinstance(body, CadBody):
        return (
            ("bounding_radius_um", body.bounding_radius_um, True),
            ("bounding_height_um", body.bounding_height_um, True),
            ("surface_area_um2", body.surface_area_um2, False),
            ("tip_area_um2", body.tip_area_um2, False),
            ("sides_area_um2", body.sides_area_um2, False),
        )
    return ()


def _body_problems(body: object, e_id: str, where: str) -> list[Problem]:
    """Dimension checks for a 3D electrode body.

    These were absent entirely: ``validate()`` inspected only ``size_um`` and
    ``pos_um``, so a body with a non-finite dimension passed the documented gate and
    then raised "Out of range float values are not JSON compliant" inside
    ``spec_hash``, and a negative ``radius_um`` made the overlap test compute a
    *widened* gap and report two touching electrodes as clear.
    """
    problems: list[Problem] = []
    for name, value, strict in _body_dims(body):
        if not _all_finite((value,)):
            problems.append(
                Problem(
                    "non-finite-value",
                    f"electrode {e_id!r} body has a non-finite {name}",
                    where=where,
                )
            )
        elif value < 0 or (strict and value == 0):
            bound = "> 0" if strict else ">= 0"
            problems.append(
                Problem(
                    "nonpositive-body-dimension",
                    f"electrode {e_id!r} body has {name}={value:g}, which must be {bound}",
                    where=where,
                )
            )
    return problems


def _electrode_problems(e: Electrode, where: str) -> list[Problem]:
    problems: list[Problem] = []
    if not _all_finite((e.size_um, *e.pos_um)):
        problems.append(
            Problem(
                "non-finite-value",
                f"electrode {e.id!r} has a non-finite position or size",
                where=where,
            )
        )
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
    if e.body is not None:
        problems += _body_problems(e.body, e.id, where)
    return problems


def _patch_depth_um(patch: RetinalPatch) -> float:
    """How far into the tissue the patch reaches from the array plane (z = 0), in µm.

    Measured as the largest |z|, which is what makes this check work for both signs.
    The project convention is **+z into the tissue** (Phase-6 D8; see
    ``spec/geometry.py`` and ``field/mesh.py``, which meshes the slab 0 <= z <= depth),
    and ``app.scene`` builds patches at +z. But this returned ``-min(zs)``, so under
    the real convention every z was positive, the result was always 0.0, and the
    ``layers-do-not-span-depth`` check below could never fire in production. A cell
    15 µm outside the meshed slab was sampled outside the solution domain and returned
    a silently wrong selectivity instead of a validation error.

    Negative z is still accepted rather than flipped: the analytical field is exactly
    mirror-symmetric across z = 0 (method of images), so legacy -z patches are valid
    on that tier, and taking the magnitude keeps them checked too.
    """
    zs = [c.soma_um[2] for c in patch.cells]
    for c in patch.cells:
        zs.extend(p[2] for p in c.axon_um)
    return max((abs(z) for z in zs), default=0.0)


# --- per-object validation (dispatch on type) ------------------------------


@singledispatch
def validate(obj: object) -> list[Problem]:
    raise TypeError(f"no validator registered for {type(obj).__name__}")


@validate.register(Electrode)
def _validate_electrode(e: Electrode) -> list[Problem]:
    return _electrode_problems(e, where=e.id)


def _placement_problems(array: ElectrodeArray) -> list[Problem]:
    """A non-finite offset/rotation passed validation and then made ``spec_hash``
    raise, because the placement was never inspected at all."""
    p = array.placement
    if p is None or _all_finite((*p.offset_um, *p.rotation_deg)):
        return []
    return [
        Problem("non-finite-value", "array placement has a non-finite value", where="placement")
    ]


@validate.register(ElectrodeArray)
def _validate_array(array: ElectrodeArray) -> list[Problem]:
    if not array.electrodes:
        return [Problem("empty-array", "electrode array has no electrodes")]

    problems: list[Problem] = _placement_problems(array)
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
            gap = math.dist(els[i].pos_um, els[j].pos_um) - (radius_um(els[i]) + radius_um(els[j]))
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
    if not _all_finite((wf.phase_width_us, wf.interphase_gap_us, wf.amplitude_scale_uA)):
        problems.append(
            Problem("non-finite-value", "waveform has a non-finite value", where="waveform")
        )
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
    weights_finite = _all_finite([w for _, w in cfg.weights])
    if not weights_finite:
        problems.append(Problem("non-finite-value", "a weight is not finite", where="weights"))
    if cfg.weights and not cfg.distant_return and weights_finite:
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
    if not math.isfinite(c.sigma_S_per_m):
        return [Problem("non-finite-value", "sigma_S_per_m is not finite")]
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
        if not _all_finite([layer.sigma_S_per_m, layer.thickness_um, *(layer.anisotropy or ())]):
            problems.append(
                Problem("non-finite-value", "layer has a non-finite value", where=where)
            )
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
