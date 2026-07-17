"""The amplitude sweep as a background job (P8 S1).

Costs the same order as the scorecard — the field is solved once per cell and every
amplitude is then a matvec — but unlike a threshold search it is not adaptive, so it
reports honest per-amplitude progress instead of two guesses.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Request

from engine.field import AnalyticalBackend
from engine.study.activation import amplitude_grid, amplitude_sweep

from ..jobs import ProgressFn
from ..models import JobStatus, SweepControls
from ..service import sweep_payload
from .score import build_scene_specs, to_job_status

router = APIRouter()


def _cache_key(c: SweepControls) -> str:
    """Keyed over the scene AND the grid — a different grid is a different answer,
    unlike the field-only preview options (extent/n), which are excluded."""
    return "sweep:" + json.dumps(
        {
            "layout": c.layout,
            "electrode_um": c.electrode_um,
            "pitch_um": c.pitch_um,
            "phase_width_us": c.phase_width_us,
            "neighbor_um": c.neighbor_um,
            "sigma_S_per_m": c.sigma_S_per_m,
            "amp_min_uA": c.amp_min_uA,
            "amp_max_uA": c.amp_max_uA,
            "n_amplitudes": c.n_amplitudes,
            "spacing": c.spacing,
        },
        sort_keys=True,
    )


@router.post("/sweep", response_model=JobStatus)
def submit_sweep(controls: SweepControls, request: Request) -> JobStatus:
    def task(report: ProgressFn) -> dict[str, object]:
        patch, array, config, conductivity = build_scene_specs(controls)
        amps = amplitude_grid(
            controls.amp_min_uA,
            controls.amp_max_uA,
            controls.n_amplitudes,
            spacing=controls.spacing,
        )
        n = len(amps)

        def on_amplitude(i: int, amp: float) -> None:
            report((i + 1) / n, f"amplitude {i + 1} of {n} ({amp:.0f} µA)")

        report(0.0, f"solving the population, then {n} amplitudes")
        sweep = amplitude_sweep(
            patch,
            array,
            config,
            conductivity,
            amplitudes_uA=amps,
            backend=AnalyticalBackend(),
            on_amplitude=on_amplitude,
        )
        return {"sweep": sweep_payload(sweep)}

    return to_job_status(request.app.state.jobs.submit(_cache_key(controls), task))
