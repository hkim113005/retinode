"""The geometry sweep → Pareto frontier, as a background job (P7 S4, P8 S4).

A sweep evaluates many geometries (each a NEURON threshold search), so it runs as a
job on the shared registry: `POST /study` submits it, and `GET /jobs/{id}` polls the
per-geometry progress and, when done, the points.

**Comparing electrode geometry is FEM-only** (the analytical point source is
diameter-blind; see docs/phase-8-findings.md), so the real path dispatches the whole
sweep to the conda FEM env (`api.study_worker`). A dev/test run with an injected
``thresholds_provider`` stays in-process and fast, because a fake provider makes the
field backend cosmetic.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..jobs import ProgressFn
from ..models import JobStatus, StudyControls, StudyResult
from ..study_core import run_study
from ..study_worker import run_study_job
from .score import to_job_status

router = APIRouter()


@router.post("/study", response_model=JobStatus)
def submit_study(controls: StudyControls, request: Request) -> JobStatus:
    # An EXPLICITLY injected provider (a dev/test fake) short-circuits the field, so
    # the sweep runs in-process, fast, no conda. Production (the default real provider)
    # must dispatch to the FEM env, because comparing electrode geometry is FEM-only.
    injected = request.app.state.provider_injected
    provider = request.app.state.thresholds_provider

    def task(report: ProgressFn):
        if injected:
            result = run_study(
                controls.model_dump(), thresholds_provider=provider, on_progress=report
            )
            return {"study": StudyResult(**result)}
        return {"study": run_study_job(controls, report)}

    job = request.app.state.jobs.submit(f"study:{controls.model_dump_json()}", task)
    return to_job_status(job)
