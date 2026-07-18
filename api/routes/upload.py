"""CAD upload: receive a STEP/BREP solid, store it, hand back an id.

The gmsh load lives in the conda FEM env (absent here), so this endpoint only
validates and stores the bytes; the id it returns is what a ``BodySpec`` of kind
``cad`` references, and the FEM job resolves it to a path and loads it. A bad solid
that passes the format check surfaces later as a job error, not here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile

from ..cad_store import CadUploadError, store_upload
from ..models import CadUploadResponse

router = APIRouter()


@router.post("/cad", response_model=CadUploadResponse)
async def upload_cad(file: UploadFile) -> CadUploadResponse:
    content = await file.read()
    try:
        upload_id, name = store_upload(file.filename or "upload", content)
    except CadUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CadUploadResponse(upload_id=upload_id, filename=name)
