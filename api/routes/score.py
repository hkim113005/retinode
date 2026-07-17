"""The scorecard as a background job (P7 S3).

The operating-window scorecard needs a NEURON threshold search — seconds, not
milliseconds — so it runs as a job, not inline. ``POST /score`` submits it (or
returns a cached result for an identical scene); ``GET /jobs/{id}`` polls progress.
The field preview stays the synchronous, NEURON-free ``/compare`` path.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from app.scene import build_scene
from engine.eval import evaluate
from engine.field import AnalyticalBackend

from ..jobs import Job, ProgressFn
from ..models import JobStatus, SceneControls
from ..service import scorecard_payload

router = APIRouter()


def _cache_key(c: SceneControls) -> str:
    """A stable key over the scene inputs that affect the score — not the field-only
    preview options (extent/n), so a re-score of the same electrode+stimulus+patch
    hits the cache."""
    return json.dumps(
        {
            "layout": c.layout,
            "electrode_um": c.electrode_um,
            "pitch_um": c.pitch_um,
            "phase_width_us": c.phase_width_us,
            "neighbor_um": c.neighbor_um,
            "sigma_S_per_m": c.sigma_S_per_m,
        },
        sort_keys=True,
    )


def to_job_status(job: Job) -> JobStatus:
    """Map a registry Job to the API status. A job's result is a keyed dict so one
    status shape carries both kinds (a score job's ``scorecard``, an accurate-field
    job's ``field`` + ``max_divergence_pct``)."""
    result = job.result or {}
    return JobStatus(
        id=job.id,
        status=job.status,  # type: ignore[arg-type]
        fraction=job.fraction,
        message=job.message,
        cached=job.cached,
        scorecard=result.get("scorecard"),
        field=result.get("field"),
        max_divergence_pct=result.get("max_divergence_pct"),
        error=job.error,
    )


@router.post("/score", response_model=JobStatus)
def submit_score(controls: SceneControls, request: Request) -> JobStatus:
    provider = request.app.state.thresholds_provider

    def task(report: ProgressFn):
        report(0.1, "placing the cell population")
        result = evaluate(
            *build_scene_specs(controls),
            backend=AnalyticalBackend(),
            thresholds_provider=provider,
        )
        report(0.95, "scoring the operating window")
        return {"scorecard": scorecard_payload(result)}

    job = request.app.state.jobs.submit(_cache_key(controls), task)
    return to_job_status(job)


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str, request: Request) -> JobStatus:
    job = request.app.state.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="no such job")
    return to_job_status(job)


def build_scene_specs(controls: SceneControls):
    scene = build_scene(
        layout=controls.layout,
        electrode_um=controls.electrode_um,
        pitch_um=controls.pitch_um,
        phase_width_us=controls.phase_width_us,
        neighbor_um=controls.neighbor_um,
        sigma_S_per_m=controls.sigma_S_per_m,
    )
    return scene.patch, scene.array, scene.config, scene.conductivity
