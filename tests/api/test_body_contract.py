"""The BodySpec contract: the discriminated 3D-body union in SceneControls."""

import pytest
from pydantic import ValidationError

from api.models import CylinderBody, NoBody, SceneControls


def test_default_scene_has_no_body_and_rejects_overlap():
    c = SceneControls()
    assert isinstance(c.body, NoBody) and c.body.kind == "none"
    assert c.overlap_policy == "reject"


def test_body_is_discriminated_on_kind():
    body = {"kind": "cylinder", "radius_um": 5.0, "height_um": 30.0, "conductive_faces": "tip"}
    c = SceneControls.model_validate({"body": body})
    assert isinstance(c.body, CylinderBody)
    assert (c.body.radius_um, c.body.height_um, c.body.conductive_faces) == (5.0, 30.0, "tip")


def test_frustum_round_trips():
    body = {"kind": "frustum", "base_radius_um": 8.0, "top_radius_um": 2.0, "height_um": 20.0}
    c = SceneControls.model_validate({"body": body})
    assert c.body.kind == "frustum" and c.body.conductive_faces == "all"


def test_cad_body_carries_the_upload_id():
    c = SceneControls.model_validate({"body": {"kind": "cad", "upload_id": "abc123"}})
    assert c.body.kind == "cad" and c.body.upload_id == "abc123"


def test_negative_dimension_is_rejected():
    body = {"kind": "cylinder", "radius_um": -1.0, "height_um": 30.0}
    with pytest.raises(ValidationError):
        SceneControls.model_validate({"body": body})


def test_bad_conductive_faces_is_rejected():
    body = {"kind": "cylinder", "radius_um": 5.0, "height_um": 30.0, "conductive_faces": "edge"}
    with pytest.raises(ValidationError):
        SceneControls.model_validate({"body": body})


def test_unknown_kind_is_rejected():
    with pytest.raises(ValidationError):
        SceneControls.model_validate({"body": {"kind": "torus", "radius_um": 5.0}})


def test_bad_overlap_policy_is_rejected():
    with pytest.raises(ValidationError):
        SceneControls.model_validate({"overlap_policy": "ignore"})
