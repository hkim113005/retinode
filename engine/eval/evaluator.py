"""The fixed evaluator: one scorer, called identically for every configuration.

``evaluate`` is the whole Gate-1 pipeline: find per-cell thresholds (the cable
engine), form the selective operating window, intersect it with the charge-safety
ceiling, and package the result with the provenance hashes that key it. It is
*fixed* — its behavior is pinned by ``EVALUATOR_VERSION``, bumped whenever the
scoring changes so old and new scores never silently mix.

The threshold computation is injected (``thresholds_provider``) so the scoring
logic is exercised without NEURON in fast tests; the default is the real
population solve.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Protocol

from engine.cable.population import PopulationThresholds, population_thresholds
from engine.field import AnalyticalBackend, FieldBackend
from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig
from engine.spec.hashing import spec_hash
from engine.store.keys import field_key, result_key

from .metrics import SOW, selective_operating_window
from .offtarget import OffTargetSet
from .overlap import OverlapPolicy
from .result import EvaluationResult, OperatingWindow
from .safety import (
    DEFAULT_SAFETY_LIMITS,
    SafetyLimits,
    SafetyReport,
    assess_safety,
    max_safe_amplitude_uA,
)

EVALUATOR_VERSION = "1"


class ThresholdsProvider(Protocol):
    """What ``evaluate`` needs to obtain per-cell thresholds for a scene."""

    def __call__(
        self,
        patch: RetinalPatch,
        array: ElectrodeArray,
        config: StimConfig,
        conductivity: ConductivityModel,
        *,
        off_target_set: OffTargetSet | None = ...,
        backend: FieldBackend | None = ...,
        overlap_policy: OverlapPolicy = ...,
        overlap_eps_um: float = ...,
    ) -> PopulationThresholds: ...


def evaluate(
    patch: RetinalPatch,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    off_target_set: OffTargetSet | None = None,
    safety_limits: SafetyLimits = DEFAULT_SAFETY_LIMITS,
    backend: FieldBackend | None = None,
    overlap_policy: OverlapPolicy = "reject",
    overlap_eps_um: float = 1.0,
    thresholds_provider: ThresholdsProvider = population_thresholds,
) -> EvaluationResult:
    """Score one configuration into a safe-and-selective operating window.

    ``overlap_policy`` handles a cell that a 3D electrode body intersects (P6 S4):
    ``"reject"`` (default) raises :class:`OverlapConflict`; ``"displace"`` severs
    the interior compartments and scores the cell on its survivors.
    """
    off_target_set = off_target_set or OffTargetSet()
    backend = backend or AnalyticalBackend()

    thresholds = thresholds_provider(
        patch,
        array,
        config,
        conductivity,
        off_target_set=off_target_set,
        backend=backend,
        overlap_policy=overlap_policy,
        overlap_eps_um=overlap_eps_um,
    )

    key = result_key(
        array,
        conductivity,
        config,
        patch,
        off_target_set,
        backend_name=backend.name,
        evaluator_version=EVALUATOR_VERSION,
    )
    fkey = field_key(array, conductivity, backend.name)

    def build(
        *,
        activated: bool,
        sow: SOW | None,
        window: OperatingWindow | None,
        safety_at_target: SafetyReport | None,
    ) -> EvaluationResult:
        return EvaluationResult(
            result_key=key,
            evaluator_version=EVALUATOR_VERSION,
            field_key=fkey,
            config_hash=spec_hash(config),
            patch_hash=spec_hash(patch),
            offtarget_hash=spec_hash(off_target_set),
            thresholds=thresholds,
            activated=activated,
            sow=sow,
            window=window,
            safety_at_target=safety_at_target,
        )

    target_uA = thresholds.target_threshold_uA
    if target_uA is None:  # the target never fired in the searched range
        return build(activated=False, sow=None, window=None, safety_at_target=None)

    sow = selective_operating_window(target_uA, thresholds.off_target_thresholds_uA)
    ceiling = max_safe_amplitude_uA(array, config, safety_limits)
    window_hi = min(sow.off_min_uA, ceiling)
    if math.isinf(window_hi):
        limiting = "none"
    elif sow.off_min_uA <= ceiling:
        limiting = "off_target"
    else:
        limiting = "safety"
    window = OperatingWindow(
        target_uA=target_uA,
        selective_hi_uA=sow.off_min_uA,
        safety_ceiling_uA=ceiling,
        window_hi_uA=window_hi,
        usable_margin_uA=window_hi - target_uA,
        limiting=limiting,
    )

    at_target = dataclasses.replace(
        config, waveform=dataclasses.replace(config.waveform, amplitude_scale_uA=target_uA)
    )
    safety_at_target = assess_safety(array, at_target, safety_limits)

    return build(activated=True, sow=sow, window=window, safety_at_target=safety_at_target)
