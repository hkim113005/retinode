"""The FEM "Run accurately" field, as a background job (P7 S3b).

The analytical field preview is synchronous (`/compare`). Solving the exact
tissue-minus-electrode field needs DOLFINx in the conda env, so it is dispatched to
that interpreter (`api.fem_worker`) as a job: `POST /field/accurate` submits it,
`GET /jobs/{id}` polls (the same registry the scorecard uses). The result carries
the FEM field grid and its divergence from the analytical preview.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..fem_worker import solve_accurate_field
from ..jobs import ProgressFn
from ..models import JobStatus, SceneControls
from .score import to_job_status

router = APIRouter()


@router.post("/field/accurate", response_model=JobStatus)
def submit_accurate_field(controls: SceneControls, request: Request) -> JobStatus:
    def task(report: ProgressFn):
        report(0.1, "meshing the tissue and solving the FEM field")
        field, divergence = solve_accurate_field(controls)
        return {"field": field, "max_divergence_pct": divergence}

    job = request.app.state.jobs.submit(f"fem:{controls.model_dump_json()}", task)
    return to_job_status(job)
