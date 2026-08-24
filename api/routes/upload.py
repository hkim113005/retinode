"""CAD upload: receive a STEP/BREP solid, store it, hand back an id.

The gmsh load lives in the conda FEM env (absent here), so this endpoint only
validates and stores the bytes; the id it returns is what a ``BodySpec`` of kind
``cad`` references, and the FEM job resolves it to a path and loads it. A bad solid
that passes the format check surfaces later as a job error, not here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile

from ..cad_measure import measure_upload
from ..cad_store import MAX_BYTES, CadUploadError, store_upload
from ..models import CadUploadResponse

router = APIRouter()

_CHUNK = 1 << 20  # 1 MiB


async def _read_capped(file: UploadFile) -> bytes:
    """Read the upload, refusing it the moment it exceeds ``MAX_BYTES``.

    ``await file.read()`` with no argument materialises the *whole* body in memory
    before ``store_upload`` ever gets to check the size — so the 25 MB limit was no
    protection at all: a multi-GB POST is a plain out-of-memory kill of the API.
    Reading in chunks and bailing at the first byte over the cap bounds the cost of
    a hostile (or fat-fingered) upload at ``MAX_BYTES`` + one chunk.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(_CHUNK):
        total += len(chunk)
        if total > MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"CAD file too large (> {MAX_BYTES} bytes)",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/cad", response_model=CadUploadResponse)
async def upload_cad(file: UploadFile) -> CadUploadResponse:
    content = await _read_capped(file)
    try:
        upload_id, name = store_upload(file.filename or "upload", content)
    except CadUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Measure the solid now, in the FEM env, and cache it beside the file: the API
    # process has no gmsh, so this is the only moment the shape can be learned without
    # a full FEM job. Returns None if that env is absent — never fails the upload.
    dims = measure_upload(upload_id) or {}
    return CadUploadResponse(
        upload_id=upload_id,
        filename=name,
        bounding_radius_um=dims.get("bounding_radius_um"),
        bounding_height_um=dims.get("bounding_height_um"),
    )
