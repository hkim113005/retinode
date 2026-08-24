"""P5 S1: parametric array geometry. Pure spec, no field/NEURON."""

from __future__ import annotations

import math

import pytest

from engine.spec.geometry import radius_um
from engine.spec.validation import has_errors, validate
from engine.study.geometry import ArrayGeometry, build_array, geometry_grid


def _min_center_distance(array) -> float:
    ps = [e.pos_um for e in array.electrodes]
    return min(math.dist(ps[i], ps[j]) for i in range(len(ps)) for j in range(i + 1, len(ps)))


def test_grid_fills_the_aperture_with_a_square_lattice():
    # aperture == pitch: centre + 4 axial neighbours (diagonals are pitch*sqrt2, out)
    g = ArrayGeometry(diameter_um=10.0, pitch_um=30.0, arrangement="grid", aperture_um=30.0)
    array = build_array(g)
    assert len(array.electrodes) == 5
    assert all(e.shape == "disk" and e.size_um == 10.0 for e in array.electrodes)
    assert _min_center_distance(array) == pytest.approx(30.0)


def test_hex_fills_the_aperture_with_a_hexagonal_lattice():
    # aperture == pitch: centre + its 6 hex neighbours
    g = ArrayGeometry(diameter_um=10.0, pitch_um=30.0, arrangement="hex", aperture_um=30.0)
    array = build_array(g)
    assert len(array.electrodes) == 7
    assert _min_center_distance(array) == pytest.approx(30.0)  # uniform nearest spacing


def test_all_centers_lie_within_the_aperture():
    g = ArrayGeometry(12.0, 25.0, "hex", aperture_um=80.0)
    array = build_array(g)
    for e in array.electrodes:
        assert math.hypot(e.pos_um[0], e.pos_um[1]) <= 80.0 + 1e-6
        assert e.pos_um[2] == 0.0  # on the array plane


def test_generated_arrays_never_overlap_and_pass_spec_validation():
    for arrangement in ("grid", "hex"):
        for pitch in (10.0, 15.0, 40.0):  # all >= diameter
            g = ArrayGeometry(10.0, pitch, arrangement, aperture_um=60.0)
            array = build_array(g)
            assert not has_errors(validate(array))
            # edge-to-edge gap is non-negative by construction
            assert _min_center_distance(array) >= 2 * radius_um(array.electrodes[0]) - 1e-9


def test_build_is_deterministic_and_geometry_is_hashable():
    g = ArrayGeometry(10.0, 30.0, "hex", 60.0)
    assert build_array(g) == build_array(g)  # same ids + positions, repeatably
    # value-equal geometries collapse in a set (a geometry is a stable key)
    assert len({g, ArrayGeometry(10.0, 30.0, "hex", 60.0)}) == 1
    assert g.label() == "hex/d10/p30/a60"


def test_ids_are_unique_and_prefixed():
    array = build_array(ArrayGeometry(10.0, 20.0, "grid", 40.0), id_prefix="E")
    ids = array.ids()
    assert len(set(ids)) == len(ids)
    assert all(i.startswith("E") for i in ids)


def test_overlapping_or_degenerate_geometry_is_rejected():
    with pytest.raises(ValueError, match="overlap"):
        build_array(ArrayGeometry(20.0, 10.0, "grid", 40.0))  # pitch < diameter
    with pytest.raises(ValueError, match="diameter"):
        build_array(ArrayGeometry(0.0, 10.0, "grid", 40.0))
    with pytest.raises(ValueError, match="arrangement"):
        build_array(ArrayGeometry(10.0, 20.0, "spiral", 40.0))  # type: ignore[arg-type]


def test_single_electrode_when_aperture_is_zero():
    array = build_array(ArrayGeometry(10.0, 30.0, "grid", aperture_um=0.0))
    assert len(array.electrodes) == 1
    assert array.electrodes[0].pos_um == (0.0, 0.0, 0.0)


def test_geometry_grid_is_the_product_minus_overlaps():
    combos = geometry_grid(
        diameters_um=[10.0, 20.0],
        pitches_um=[10.0, 15.0, 30.0],
        arrangement="grid",
        aperture_um=50.0,
    )
    pairs = {(c.diameter_um, c.pitch_um) for c in combos}
    assert pairs == {(10.0, 10.0), (10.0, 15.0), (10.0, 30.0), (20.0, 30.0)}
    assert all(c.arrangement == "grid" and c.aperture_um == 50.0 for c in combos)


def test_pillar_geometry_grid_attaches_cylinders_and_sweeps_height():
    from engine.spec import Cylinder
    from engine.study.geometry import pillar_geometry_grid

    combos = pillar_geometry_grid(
        diameters_um=[10.0, 20.0],
        pitches_um=[15.0, 40.0],
        heights_um=[20.0, 40.0],
        arrangement="grid",
        aperture_um=50.0,
    )
    # (20,15) drops (overlap); the rest x 2 heights
    triples = {(c.diameter_um, c.pitch_um, c.body.height_um) for c in combos}
    assert (20.0, 15.0, 20.0) not in triples  # overlapping pitch dropped
    assert (10.0, 40.0, 40.0) in triples
    assert all(isinstance(c.body, Cylinder) for c in combos)
    assert all(c.body.radius_um == c.diameter_um / 2.0 for c in combos)


def test_build_array_attaches_the_geometry_body_to_every_electrode():
    from engine.spec import Cylinder
    from engine.study.geometry import ArrayGeometry, build_array

    geom = ArrayGeometry(10.0, 30.0, "grid", 30.0, "disk", Cylinder(5.0, 20.0))
    array = build_array(geom)
    assert all(e.body == Cylinder(5.0, 20.0) for e in array.electrodes)
