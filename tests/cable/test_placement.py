"""S6a: placing a cell in the patch. Position + axon orientation."""

import pytest

from engine import spec
from engine.cable.placement import axon_direction, place_cell

# --- fast: the pure axon-direction logic ---


def test_axon_direction_toward_optic_disc():
    r = spec.RGC(id="t", cell_type="x", soma_um=(100.0, 50.0, -20.0))
    d = axon_direction(r, (2000.0, 50.0, -20.0))
    assert d[0] > 0 and abs(d[1]) < 1e-9  # points +x toward the disc


def test_axon_direction_prefers_axon_um():
    r = spec.RGC(
        id="t",
        cell_type="x",
        soma_um=(0.0, 0.0, 0.0),
        axon_um=((0.0, 0.0, 0.0), (0.0, -100.0, 0.0)),
    )
    d = axon_direction(r, (2000.0, 0.0, 0.0))
    assert d[1] < 0  # follows axon_um (-y), not the optic disc (+x)


def test_axon_direction_defaults_to_x():
    r = spec.RGC(id="t", cell_type="x", soma_um=(0.0, 0.0, 0.0))
    assert axon_direction(r, None) == (1.0, 0.0, 0.0)


# --- neuron: the placed cell's coordinates ---


@pytest.mark.neuron
def test_placed_cell_lands_at_soma_and_axon_points_out(neuron_h):
    from engine.cable.drive import segment_coords

    r = spec.RGC(id="t", cell_type="parasol_on", soma_um=(100.0, 50.0, -20.0))
    cell = place_cell(r, optic_disc=(2000.0, 50.0, -20.0))
    coords, segs = segment_coords(cell)

    soma_i = next(i for i, s in enumerate(segs) if s.sec == cell.soma_sec)
    assert coords[soma_i] == pytest.approx([100.0, 50.0, -20.0], abs=1.0)
    assert coords[:, 0].max() > 300.0  # axon reaches toward the optic disc (+x)
