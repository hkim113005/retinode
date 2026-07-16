"""P6 S2: 3D electrode bodies — geometry, conductive area, and serialization."""

import math

import pytest

from engine.spec import Cylinder, Electrode, Frustum, Hemisphere, from_json, spec_hash, to_json
from engine.spec.body import body_base_radius_um, body_conductive_area_um2
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
