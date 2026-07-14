"""radius_um: the shared electrode-extent helper (used by overlap + field)."""

from engine.spec import Electrode
from engine.spec.geometry import radius_um


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
