"""The Compare endpoint: one configuration scored on one patch.

``POST /compare`` builds the scene from the controls, returns the analytical field
grid synchronously, and — only if asked — runs the evaluator for the operating-
window scorecard. The field path never touches NEURON; the scorecard does, through
the app's threshold provider (a fast fake in tests; the real population solve in
production, which S3 moves to a background job).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.scene import body_from_spec, build_scene
from engine.eval import evaluate
from engine.field import AnalyticalBackend

from ..models import CompareResponse, SceneControls
from ..service import (
    cell_markers,
    electrode_markers,
    field_grid_payload,
    scorecard_payload,
)

router = APIRouter()


@router.post("/compare", response_model=CompareResponse)
def compare(controls: SceneControls, request: Request) -> CompareResponse:
    # Thread a primitive body through so the electrode markers reflect its footprint
    # (the loupe draws the true 3D shape from them). The analytical field itself stays
    # geometry-blind — a bodied scene is FEM-only, and the client shows a Run-FEM prompt
    # instead of this field. CAD needs gmsh (absent here), so it falls back to the flat
    # footprint for the marker; its real field/scorecard come from the FEM dispatch.
    body = None if controls.body.kind == "cad" else body_from_spec(controls.body.model_dump())
    scene = build_scene(
        layout=controls.layout,
        electrode_um=controls.electrode_um,
        pitch_um=controls.pitch_um,
        phase_width_us=controls.phase_width_us,
        neighbor_um=controls.neighbor_um,
        sigma_S_per_m=controls.sigma_S_per_m,
        body=body,
    )
    field = field_grid_payload(
        scene.array, scene.config, scene.conductivity, extent_um=controls.extent_um, n=controls.n
    )
    scorecard = None
    if controls.include_scorecard:
        result = evaluate(
            scene.patch,
            scene.array,
            scene.config,
            scene.conductivity,
            backend=AnalyticalBackend(),
            thresholds_provider=request.app.state.thresholds_provider,
        )
        scorecard = scorecard_payload(result)
    return CompareResponse(
        field=field,
        electrodes=electrode_markers(scene.array),
        cells=cell_markers(scene.patch),
        scorecard=scorecard,
    )
