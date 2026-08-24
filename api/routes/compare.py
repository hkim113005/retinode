"""The Compare endpoint: one configuration scored on one patch.

``POST /compare`` builds the scene from the controls, returns the analytical field
grid synchronously, and — only if asked — runs the evaluator for the operating-
window scorecard. The field path never touches NEURON; the scorecard does, through
the app's threshold provider (a fast fake in tests; the real population solve in
production, which S3 moves to a background job).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.scene import body_from_spec, build_scene
from engine.eval import evaluate
from engine.eval.overlap import OverlapConflict
from engine.field import AnalyticalBackend

from ..cad_store import read_dims
from ..models import CompareResponse, MarkerBody, SceneControls
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
        # This scorecard is analytical, and the analytical tier cannot see a body. It
        # would have returned the FLAT-disk operating window for a 3D electrode — the
        # same silent-wrong-answer /sweep had. ``POST /score`` already dispatches a
        # bodied scene to the FEM env; send the caller there instead of answering wrong.
        if controls.body.kind != "none":
            raise HTTPException(
                status_code=422,
                detail=(
                    "a scorecard for a 3D electrode body is FEM-only — the analytical "
                    "field this endpoint uses is blind to electrode geometry. Submit "
                    "POST /score, which runs the bodied scene on FEM as a job."
                ),
            )
        try:
            result = evaluate(
                scene.patch,
                scene.array,
                scene.config,
                scene.conductivity,
                backend=AnalyticalBackend(),
                thresholds_provider=request.app.state.thresholds_provider,
                overlap_policy=controls.overlap_policy,
            )
        except OverlapConflict as exc:
            # The caller's own overlap_policy was being dropped on the floor here, so a
            # request that already said "displace" still got the reject-path error --
            # advice it had followed. Honour the policy, and surface a genuine conflict
            # as the client error it is rather than a 500.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        scorecard = scorecard_payload(result)
    return CompareResponse(
        field=field,
        electrodes=_with_cad_marker(electrode_markers(scene.array), controls),
        cells=cell_markers(scene.patch),
        scorecard=scorecard,
    )


def _with_cad_marker(markers: list, controls: SceneControls) -> list:
    """Attach the CAD solid's bounding cylinder to the driven electrode's marker.

    ``build_scene`` above is handed ``body=None`` for a CAD electrode, because
    resolving one needs gmsh and this process has none — so its marker comes back
    bodyless and the 3D loupe drew a flat disk for it. That is a claim the tool cannot
    support: a flat disk is a specific shape, and the uploaded solid is not it.

    The dimensions were measured once at upload and cached beside the file, so they
    are readable here without gmsh. ``MarkerBody(kind="cad")`` is exactly the case its
    own docstring already describes ("A CAD solid is drawn as its bounding cylinder"),
    and the loupe's cylinder branch already renders it. Still ``None`` when the solid
    was never measured (no FEM env at upload) — the loupe then says the shape needs
    FEM rather than inventing one.
    """
    if controls.body.kind != "cad" or not markers:
        return markers
    dims = read_dims(controls.body.upload_id)
    if not dims:
        return markers
    r, h = dims.get("bounding_radius_um"), dims.get("bounding_height_um")
    if not r or not h:
        return markers
    # e0 is the driven electrode the body shapes (see build_scene).
    markers[0] = markers[0].model_copy(
        update={"body": MarkerBody(kind="cad", radius_um=float(r), height_um=float(h))}
    )
    return markers
