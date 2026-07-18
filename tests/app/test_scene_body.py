"""A UI path for custom shapes: the scene builder attaching a 3D body to e0.

The body is what makes an electrode FEM-only (the analytical tier is a point source
blind to it). These tests cover the pure uv-env translation — a contract body dict to
an ``engine.spec`` primitive, attached to the driven electrode — with no gmsh/FEM."""

import pytest

from app.scene import body_from_spec, build_array, build_scene
from engine import spec


def test_no_body_dict_is_a_flat_electrode():
    assert body_from_spec(None) is None
    assert body_from_spec({"kind": "none"}) is None


def test_hemisphere_from_spec():
    b = body_from_spec({"kind": "hemisphere", "radius_um": 10.0})
    assert b == spec.Hemisphere(radius_um=10.0)


def test_cylinder_from_spec_carries_conductive_faces():
    b = body_from_spec(
        {"kind": "cylinder", "radius_um": 5.0, "height_um": 30.0, "conductive_faces": "tip"}
    )
    assert b == spec.Cylinder(radius_um=5.0, height_um=30.0, conductive_faces="tip")


def test_cylinder_defaults_conductive_faces_to_all():
    b = body_from_spec({"kind": "cylinder", "radius_um": 5.0, "height_um": 30.0})
    assert isinstance(b, spec.Cylinder) and b.conductive_faces == "all"


def test_frustum_from_spec():
    b = body_from_spec(
        {
            "kind": "frustum",
            "base_radius_um": 8.0,
            "top_radius_um": 2.0,
            "height_um": 20.0,
            "conductive_faces": "sides",
        }
    )
    assert b == spec.Frustum(
        base_radius_um=8.0, top_radius_um=2.0, height_um=20.0, conductive_faces="sides"
    )


def test_cad_must_be_resolved_in_the_fem_env():
    # CAD needs gmsh to read the solid; the uv-env helper refuses rather than guess.
    with pytest.raises(ValueError, match="load_cad_body"):
        body_from_spec({"kind": "cad", "upload_id": "abc", "conductive_faces": "all"})


def test_unknown_kind_raises():
    with pytest.raises(ValueError, match="unknown electrode body kind"):
        body_from_spec({"kind": "torus"})


def test_build_array_attaches_body_to_the_driven_electrode():
    body = spec.Cylinder(radius_um=5.0, height_um=30.0, conductive_faces="tip")
    a = build_array("single", 10.0, 60.0, body=body)
    assert a.electrodes[0].body is body


def test_bipolar_bodies_the_driven_electrode_only():
    body = spec.Hemisphere(radius_um=10.0)
    a = build_array("bipolar", 12.0, 80.0, body=body)
    assert a.electrodes[0].id == "e0" and a.electrodes[0].body is body
    assert a.electrodes[1].id == "e1" and a.electrodes[1].body is None  # the return stays flat


def test_build_scene_threads_the_body_through():
    scene = build_scene(
        layout="single",
        electrode_um=10.0,
        pitch_um=60.0,
        phase_width_us=200.0,
        neighbor_um=40.0,
        sigma_S_per_m=1.0,
        body=spec.Cylinder(radius_um=5.0, height_um=30.0, conductive_faces="tip"),
    )
    assert scene.array.electrodes[0].body == spec.Cylinder(
        radius_um=5.0, height_um=30.0, conductive_faces="tip"
    )


def test_build_scene_default_is_flat():
    scene = build_scene(
        layout="single",
        electrode_um=10.0,
        pitch_um=60.0,
        phase_width_us=200.0,
        neighbor_um=40.0,
        sigma_S_per_m=1.0,
    )
    assert scene.array.electrodes[0].body is None
