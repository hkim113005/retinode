"""P6 S2: 3D electrode bodies (geometry, conductive area, and serialization)."""

import math

import pytest

from engine.spec import Cylinder, Electrode, Frustum, Hemisphere, from_json, spec_hash, to_json
from engine.spec.body import (
    body_base_radius_um,
    body_conductive_area_um2,
    point_in_body,
    surface_distance_um,
)
from engine.spec.geometry import electrode_area_um2, radius_um


def _with_body(body):
    return Electrode(id="E", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=0.0, body=body)


def test_conductive_area_hemisphere():
    assert body_conductive_area_um2(Hemisphere(10.0)) == pytest.approx(2 * math.pi * 100)


def test_conductive_area_cylinder_by_faces():
    r, h = 5.0, 20.0
    tip, sides = math.pi * r * r, 2 * math.pi * r * h
    assert body_conductive_area_um2(Cylinder(r, h, "tip")) == pytest.approx(tip)
    assert body_conductive_area_um2(Cylinder(r, h, "sides")) == pytest.approx(sides)
    assert body_conductive_area_um2(Cylinder(r, h, "all")) == pytest.approx(tip + sides)


def test_conductive_area_frustum_uses_slant_height():
    r0, r1, h = 8.0, 4.0, 20.0
    slant = math.hypot(h, r0 - r1)
    assert body_conductive_area_um2(Frustum(r0, r1, h, "sides")) == pytest.approx(
        math.pi * (r0 + r1) * slant
    )
    assert body_conductive_area_um2(Frustum(r0, r1, h, "tip")) == pytest.approx(math.pi * r1 * r1)


def test_base_radius_is_the_lateral_extent_at_the_plane():
    assert body_base_radius_um(Hemisphere(10.0)) == 10.0
    assert body_base_radius_um(Cylinder(5.0, 20.0)) == 5.0
    assert body_base_radius_um(Frustum(8.0, 4.0, 20.0)) == 8.0  # base, not top


def test_electrode_area_and_radius_defer_to_the_body():
    e = _with_body(Hemisphere(10.0))
    assert electrode_area_um2(e) == pytest.approx(2 * math.pi * 100)  # conductive surface
    assert radius_um(e) == 10.0  # lateral radius, not size_um/2


def test_body_electrode_round_trips_and_hashes_stably():
    for body in (Hemisphere(10.0), Cylinder(5.0, 20.0, "tip"), Frustum(8.0, 4.0, 20.0, "sides")):
        e = _with_body(body)
        back = from_json(to_json(e))
        assert back == e  # the multi-arm ElectrodeBody union decodes by __type__
        assert spec_hash(back) == spec_hash(e)
        assert type(back.body) is type(body)


def test_a_body_makes_the_electrode_hash_differ_from_the_flat_one():
    flat = Electrode(id="E", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=20.0)
    assert spec_hash(flat) != spec_hash(_with_body(Cylinder(10.0, 20.0)))


# --- point-in-body + surface distance (P6 S4 overlap predicates) -------------


def test_point_in_hemisphere_is_the_upper_half_ball():
    h = Hemisphere(10.0)
    assert point_in_body(h, 0.0, 0.0, 5.0)  # on the axis, inside
    assert point_in_body(h, 6.0, 0.0, 6.0)  # rho^2+z^2 = 72 < 100
    assert not point_in_body(h, 0.0, 0.0, 12.0)  # too deep
    assert not point_in_body(h, 0.0, 0.0, -1.0)  # below the plane (not in the z>=0 half)


def test_point_in_cylinder_is_the_capped_pillar():
    c = Cylinder(5.0, 30.0)
    assert point_in_body(c, 0.0, 0.0, 15.0)
    assert point_in_body(c, 4.9, 0.0, 0.1)
    assert not point_in_body(c, 5.1, 0.0, 15.0)  # radially outside
    assert not point_in_body(c, 0.0, 0.0, 31.0)  # past the tip


def test_point_in_frustum_follows_the_taper():
    f = Frustum(base_radius_um=8.0, top_radius_um=2.0, height_um=20.0)
    assert point_in_body(f, 7.0, 0.0, 0.5)  # near the wide base
    assert not point_in_body(f, 7.0, 0.0, 18.0)  # the wall has narrowed by depth 18
    assert point_in_body(f, 1.5, 0.0, 18.0)  # inside the narrow tip


def test_surface_distance_sign_and_magnitude():
    c = Cylinder(5.0, 30.0)
    assert surface_distance_um(c, 0.0, 0.0, 15.0) < 0  # inside -> negative
    assert surface_distance_um(c, 8.0, 0.0, 15.0) == pytest.approx(3.0)  # 3 um outside the wall
    h = Hemisphere(10.0)
    assert surface_distance_um(h, 0.0, 0.0, 13.0) == pytest.approx(3.0)  # 3 um past the dome


# --- CadBody: imported CAD electrode (P6 S5) ---------------------------------


def _cad(content_hash="abc123", r=5.0, h=30.0, area=1021.0):
    from engine.spec import CadBody

    return CadBody(
        cad_path="/tmp/x.step",
        content_hash=content_hash,
        bounding_radius_um=r,
        bounding_height_um=h,
        surface_area_um2=area,
    )


def test_cad_body_defers_to_its_measured_summaries():
    c = _cad(r=7.0, area=900.0)
    assert body_base_radius_um(c) == 7.0
    assert body_conductive_area_um2(c) == 900.0  # measured surface, for charge density


def test_cad_overlap_uses_the_bounding_cylinder():
    c = _cad(r=5.0, h=30.0)
    assert point_in_body(c, 0.0, 0.0, 15.0)  # inside the bounding cylinder
    assert not point_in_body(c, 6.0, 0.0, 15.0)  # outside the radius
    assert not point_in_body(c, 0.0, 0.0, 31.0)  # past the height


def test_cad_content_hash_is_the_geometric_identity():
    a = _with_body(_cad(content_hash="hashA"))
    b = _with_body(_cad(content_hash="hashB"))
    assert spec_hash(a) != spec_hash(b)  # different CAD content -> distinct key
    assert spec_hash(a) == spec_hash(_with_body(_cad(content_hash="hashA")))


def test_cad_body_round_trips():
    e = _with_body(_cad())
    assert from_json(to_json(e)) == e


def _box_trimesh(hx, hy, z0, z1):
    """8 corners + 12 triangles of the box [-hx,hx] x [-hy,hy] x [z0,z1]."""
    v = [
        (-hx, -hy, z0), (hx, -hy, z0), (hx, hy, z0), (-hx, hy, z0),
        (-hx, -hy, z1), (hx, -hy, z1), (hx, hy, z1), (-hx, hy, z1),
    ]
    faces = [
        (0, 1, 2), (0, 2, 3),  # bottom
        (4, 6, 5), (4, 7, 6),  # top
        (0, 4, 5), (0, 5, 1),  # -y
        (1, 5, 6), (1, 6, 2),  # +x
        (2, 6, 7), (2, 7, 3),  # +y
        (3, 7, 4), (3, 4, 0),  # -x
    ]
    return tuple(v), tuple(faces)


def _square_pillar_cad(hx=2.0, hy=2.0, z1=20.0):
    from engine.spec import CadBody

    pts, tris = _box_trimesh(hx, hy, 0.0, z1)
    return CadBody(
        cad_path="/tmp/sq.step", content_hash="sq", bounding_radius_um=max(hx, hy),
        bounding_height_um=z1, surface_area_um2=0.0,
        surface_points_um=pts, surface_tris=tris,
    )


def test_exact_cad_overlap_catches_a_corner_the_bounding_cylinder_misses():
    # P6 S9: a square pillar's corner sticks out past its bounding *cylinder*, so the
    # old rho<=bounding_radius test under-flags it; the triangulated test is exact.
    pillar = _square_pillar_cad(hx=2.0, hy=2.0, z1=20.0)
    corner = (1.8, 1.8, 10.0)  # inside the square, but rho=2.55 > bounding_radius 2
    assert point_in_body(pillar, *corner)  # exact: inside the metal
    # the same body with no triangulation falls back to the bounding cylinder, which
    # wrongly reports the corner as outside (rho exceeds the radius)
    from engine.spec import CadBody

    no_mesh = CadBody(
        cad_path="/tmp/sq.step", content_hash="sq", bounding_radius_um=2.0,
        bounding_height_um=20.0, surface_area_um2=0.0,
    )
    assert not point_in_body(no_mesh, *corner)  # bounding-cylinder fallback disagrees


def test_triangulated_cad_body_round_trips():
    e = _with_body(_square_pillar_cad())
    back = from_json(to_json(e))
    assert back == e  # the baked triangulation survives serialization
    assert type(back.body.surface_tris[0]) is tuple  # nested tuples, not lists


def test_exact_cad_overlap_inside_outside_and_signed_distance():
    pillar = _square_pillar_cad(hx=2.0, hy=2.0, z1=20.0)
    assert point_in_body(pillar, 0.0, 0.0, 10.0)  # axis, inside
    assert not point_in_body(pillar, 0.0, 0.0, 25.0)  # above the top
    assert not point_in_body(pillar, 5.0, 0.0, 10.0)  # well outside
    # signed distance: negative inside, positive outside, ~exact magnitude
    assert surface_distance_um(pillar, 0.0, 0.0, 10.0) < 0.0
    # 2 um past the +x wall (which sits at x=2)
    assert surface_distance_um(pillar, 4.0, 0.0, 10.0) == pytest.approx(2.0, abs=1e-6)


def test_cad_conductive_area_honors_the_face_group():
    from engine.spec import CadBody

    def cad(faces):
        return CadBody(
            cad_path="/tmp/x.step", content_hash="h", bounding_radius_um=5.0,
            bounding_height_um=30.0, surface_area_um2=1021.0,
            conductive_faces=faces, tip_area_um2=78.5, sides_area_um2=942.5,
        )

    assert body_conductive_area_um2(cad("all")) == pytest.approx(1021.0)  # total
    assert body_conductive_area_um2(cad("tip")) == pytest.approx(78.5)  # deep cap only
    assert body_conductive_area_um2(cad("sides")) == pytest.approx(942.5)  # lateral only
