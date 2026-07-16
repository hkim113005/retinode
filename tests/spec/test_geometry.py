"""radius_um / electrode_outline / electrode_area_um2: shared electrode geometry."""

import math

import pytest

from engine.spec import Electrode
from engine.spec.geometry import electrode_area_um2, electrode_outline, radius_um


def _sq(size=10.0, x=0.0, y=0.0):
    return Electrode(id="s", pos_um=(x, y, 0.0), shape="square", size_um=size)


def _hex(size=10.0):
    return Electrode(id="h", pos_um=(0.0, 0.0, 0.0), shape="hex", size_um=size)


def _disk(size=10.0):
    return Electrode(id="d", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=size)


def _poly(verts):
    return Electrode(id="p", pos_um=(0.0, 0.0, 0.0), shape="poly", size_um=0.0, boundary_um=verts)


def test_radius_um_is_half_size_for_disk_square_hex():
    assert radius_um(Electrode(id="d", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)) == 5.0
    assert radius_um(Electrode(id="s", pos_um=(0.0, 0.0, 0.0), shape="square", size_um=8.0)) == 4.0


def test_radius_um_poly_uses_max_vertex_distance():
    e = Electrode(
        id="p",
        pos_um=(0.0, 0.0, 0.0),
        shape="poly",
        size_um=0.0,
        boundary_um=((10.0, 0.0, 0.0), (-10.0, 0.0, 0.0), (0.0, 6.0, 0.0)),
    )
    assert radius_um(e) == 10.0


def test_radius_um_poly_without_boundary_is_zero():
    e = Electrode(id="p", pos_um=(0.0, 0.0, 0.0), shape="poly", size_um=0.0)
    assert radius_um(e) == 0.0


# --- electrode_outline: the shared face outline the FEM mesh imprints ---------


def test_disk_has_no_polygon_outline():
    assert electrode_outline(_disk()) is None


def test_square_outline_is_four_centred_corners():
    outline = electrode_outline(_sq(size=10.0, x=3.0, y=0.0))
    assert outline is not None and len(outline) == 4
    assert set(outline) == {(-2.0, -5.0), (8.0, -5.0), (8.0, 5.0), (-2.0, 5.0)}


def test_hex_outline_is_six_vertices_at_the_circumradius():
    outline = electrode_outline(_hex(size=10.0))
    assert outline is not None and len(outline) == 6
    r_circ = 10.0 / math.sqrt(3.0)
    assert all(math.hypot(vx, vy) == pytest.approx(r_circ) for vx, vy in outline)


def test_poly_outline_is_the_boundary_xy():
    e = _poly(((5.0, -5.0, 0.0), (5.0, 5.0, 0.0), (-5.0, 5.0, 0.0), (-5.0, -5.0, 0.0)))
    assert electrode_outline(e) == ((5.0, -5.0), (5.0, 5.0), (-5.0, 5.0), (-5.0, -5.0))


# --- electrode_area_um2: one source of truth for shape area ------------------


def test_area_matches_the_closed_forms():
    assert electrode_area_um2(_disk(10.0)) == pytest.approx(math.pi * 25.0)
    assert electrode_area_um2(_sq(10.0)) == pytest.approx(100.0)
    assert electrode_area_um2(_hex(10.0)) == pytest.approx((math.sqrt(3.0) / 2.0) * 100.0)


def test_poly_area_is_the_shoelace_of_the_outline():
    tri = _poly(((0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 6.0, 0.0)))
    assert electrode_area_um2(tri) == pytest.approx(30.0)  # 1/2 * 10 * 6
    assert electrode_area_um2(_poly(())) == 0.0  # no outline -> zero area
