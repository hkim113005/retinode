"""The geometry sweep → Pareto frontier, as a background job (P7 S4).

A sweep evaluates many geometries (each a NEURON threshold search), so it runs as a
job on the shared registry — `POST /study` submits it, `GET /jobs/{id}` polls the
per-geometry progress and, when done, the points. Each point carries its cost (the
target threshold), its selective window, whether it is charge-safe, and whether it
sits on the selectivity-versus-cost frontier.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.scene import build_patch
from engine.spec import HomogeneousConductivity
from engine.study.geometry import geometry_grid
from engine.study.geometry_sweep import GeometrySweepResult, geometry_sweep, monopolar_center

from ..jobs import ProgressFn
from ..models import JobStatus, StudyControls, StudyPoint, StudyResult
from .score import to_job_status

router = APIRouter()


def _points(sweep: GeometrySweepResult) -> StudyResult:
    # Gather (cost = target threshold, selectivity = usable window) per activated
    # geometry, then mark the **selectivity-versus-cost** frontier: a safe point is
    # on it if no other safe point beats it on both axes (lower cost, higher
    # selectivity). This is the master-plan §15 frontier — distinct from the engine's
    # selectivity-vs-safety `pareto`.
    raw = [
        {
            "diameter_um": o.geometry.diameter_um,
            "pitch_um": o.geometry.pitch_um,
            "cost_uA": r.window.target_uA,
            "selectivity_uA": r.window.usable_margin_uA,
            "safe": bool(r.safety_at_target and r.safety_at_target.safe),
        }
        for o in sweep.outcomes
        for r in o.results
        if r.activated and r.window is not None
    ]

    def dominated(p: dict) -> bool:
        return any(
            q is not p
            and q["safe"]
            and q["cost_uA"] <= p["cost_uA"]
            and q["selectivity_uA"] >= p["selectivity_uA"]
            and (q["cost_uA"] < p["cost_uA"] or q["selectivity_uA"] > p["selectivity_uA"])
            for q in raw
        )

    points = [StudyPoint(**p, on_frontier=p["safe"] and not dominated(p)) for p in raw]
    return StudyResult(points=points, n_geometries=sweep.n_geometries)


@router.post("/study", response_model=JobStatus)
def submit_study(controls: StudyControls, request: Request) -> JobStatus:
    provider = request.app.state.thresholds_provider

    def task(report: ProgressFn):
        geometries = geometry_grid(
            diameters_um=controls.diameters_um,
            pitches_um=controls.pitches_um,
            arrangement=controls.arrangement,
            aperture_um=controls.aperture_um,
        )
        n = max(1, len(geometries))
        patch = build_patch(controls.neighbor_um)
        conductivity = HomogeneousConductivity(sigma_S_per_m=controls.sigma_S_per_m)

        def config_factory(array):
            return monopolar_center(array, phase_width_us=controls.phase_width_us)

        def on_geometry(index: int, _outcome) -> None:
            report((index + 1) / n, f"solving geometry {index + 1} of {n}")

        report(0.02, f"sweeping {n} geometries")
        sweep = geometry_sweep(
            geometries,
            patch,
            conductivity,
            config_factory,
            thresholds_provider=provider,
            on_geometry=on_geometry,
        )
        return {"study": _points(sweep)}

    job = request.app.state.jobs.submit(f"study:{controls.model_dump_json()}", task)
    return to_job_status(job)
