"""CAD upload: the content-addressed store + the POST /cad endpoint.

The gmsh load is conda-only (covered by the load_cad_body fem tests); here we cover
the uv-side gate — accept STEP/BREP, reject STL/oversize/empty, round-trip the id, and
refuse path traversal."""

import pytest
from fastapi.testclient import TestClient

from api import create_app
from api.cad_store import MAX_BYTES, CadUploadError, resolve_upload, store_upload


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("RETINODE_CAD_DIR", str(tmp_path))


def test_store_accepts_step_and_round_trips():
    upload_id, name = store_upload("pillar.step", b"ISO-10303-21;\n...solid...")
    assert upload_id.endswith(".step")
    assert name == "pillar.step"
    path = resolve_upload(upload_id)
    assert path.endswith(upload_id)


def test_identical_bytes_are_content_addressed():
    a, _ = store_upload("a.step", b"same-bytes")
    b, _ = store_upload("b.step", b"same-bytes")  # different name, same content
    assert a == b  # one file, one id


def test_stl_is_rejected_as_not_a_solid():
    with pytest.raises(CadUploadError, match="STL"):
        store_upload("mesh.stl", b"solid ...")


def test_empty_file_is_rejected():
    with pytest.raises(CadUploadError, match="empty"):
        store_upload("x.step", b"")


def test_oversize_is_rejected():
    with pytest.raises(CadUploadError, match="too large"):
        store_upload("big.brep", b"x" * (MAX_BYTES + 1))


def test_resolve_refuses_path_traversal():
    with pytest.raises(CadUploadError, match="invalid"):
        resolve_upload("../../etc/passwd")


def test_resolve_unknown_id_is_a_clear_error():
    with pytest.raises(CadUploadError, match="unknown"):
        resolve_upload("deadbeef.step")


def test_post_cad_endpoint_stores_and_returns_an_id():
    client = TestClient(create_app())
    r = client.post("/cad", files={"file": ("pillar.step", b"ISO-10303-21;", "application/step")})
    assert r.status_code == 200
    body = r.json()
    assert body["upload_id"].endswith(".step")
    assert body["filename"] == "pillar.step"


def test_post_cad_rejects_stl_with_422():
    client = TestClient(create_app())
    r = client.post("/cad", files={"file": ("mesh.stl", b"solid", "model/stl")})
    assert r.status_code == 422
    assert "STL" in r.json()["detail"]


def test_post_cad_refuses_oversize_without_buffering_it_all():
    """The endpoint must bail *during* the read, not after materialising the body.

    Guards the fix for the unbounded ``await file.read()``: the cap is enforced
    chunk by chunk, so an oversize POST costs MAX_BYTES + one chunk, not the whole
    body. 413 (not 422) — this is a size limit, not a malformed payload.
    """
    client = TestClient(create_app())
    r = client.post(
        "/cad", files={"file": ("big.step", b"x" * (MAX_BYTES + 1), "application/step")}
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"]
