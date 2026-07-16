"""P4 S1 (fast): the mesh *geometry* -- partition, validation, sizing -- with no
gmsh and no solve. The gmsh build itself is covered in test_mesh_fem.py (fem)."""

from __future__ import annotations

import math

import pytest

from engine.field import mesh as M
from engine.spec import (
    ElectrodeArray,
    HomogeneousConductivity,
    LayeredConductivity,
)
from engine.spec.conductivity import Layer
from engine.spec.geometry import Electrode


def _disk(id: str, x: float, y: float, d: float = 10.0) -> Electrode:
    return Electrode(id=id, pos_um=(x, y, 0.0), shape="disk", size_um=d)


def _array(*es: Electrode) -> ElectrodeArray:
    return ElectrodeArray(electrodes=tuple(es))


HOMOG = HomogeneousConductivity(sigma_S_per_m=1.0)


def test_layer_partition_homogeneous_is_one_full_depth_slab():
    dom = M.FieldDomain(_array(_disk("A", 0, 0)), HOMOG, 100.0, 60.0, 2.0, 25.0)
    slabs = M.layer_partition(dom)
    assert len(slabs) == 1
    (s,) = slabs
    assert (s.z0_um, s.z1_um, s.sigma_S_per_m) == (0.0, 60.0, 1.0)
    assert s.anisotropy is None


def test_layer_partition_layered_stacks_from_the_surface_down():
    cond = LayeredConductivity(
        layers=(
            Layer(sigma_S_per_m=1.0, thickness_um=20.0),
            Layer(sigma_S_per_m=0.3, thickness_um=30.0, anisotropy=(0.3, 0.3, 0.1)),
        )
    )
    dom = M.FieldDomain(_array(_disk("A", 0, 0)), cond, 100.0, 50.0, 2.0, 25.0)
    slabs = M.layer_partition(dom)
    assert [(s.z0_um, s.z1_um) for s in slabs] == [(0.0, 20.0), (20.0, 50.0)]
    assert slabs[1].anisotropy == (0.3, 0.3, 0.1)


def test_layer_partition_rejects_thickness_depth_mismatch():
    cond = LayeredConductivity(layers=(Layer(sigma_S_per_m=1.0, thickness_um=20.0),))
    dom = M.FieldDomain(_array(_disk("A", 0, 0)), cond, 100.0, 50.0, 2.0, 25.0)
    with pytest.raises(ValueError, match="must match"):
        M.layer_partition(dom)


def test_validate_domain_accepts_every_supported_2d_shape():
    sq = Electrode(id="S", pos_um=(-20.0, 0.0, 0.0), shape="square", size_um=10.0)
    hx = Electrode(id="H", pos_um=(20.0, 0.0, 0.0), shape="hex", size_um=10.0)
    poly = Electrode(
        id="P",
        pos_um=(0.0, 30.0, 0.0),
        shape="poly",
        size_um=0.0,
        boundary_um=((-5.0, 25.0, 0.0), (5.0, 25.0, 0.0), (0.0, 35.0, 0.0)),
    )
    M.validate_domain(
        M.FieldDomain(_array(sq, hx, poly), HOMOG, 100.0, 60.0, 2.0, 25.0)
    )  # no raise


def test_validate_domain_rejects_geometry_mistakes():
    good = M.FieldDomain(_array(_disk("A", 0, 0)), HOMOG, 100.0, 60.0, 2.0, 25.0)
    M.validate_domain(good)  # no raise

    # an unknown shape (poly is fine; "blob" is not)
    blob = Electrode(id="B", pos_um=(0.0, 0.0, 0.0), shape="blob", size_um=10.0)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="supports"):
        M.validate_domain(M.FieldDomain(_array(blob), HOMOG, 100.0, 60.0, 2.0, 25.0))

    # a polygon electrode without an outline
    bad_poly = Electrode(id="P", pos_um=(0.0, 0.0, 0.0), shape="poly", size_um=0.0)
    with pytest.raises(ValueError, match="boundary_um"):
        M.validate_domain(M.FieldDomain(_array(bad_poly), HOMOG, 100.0, 60.0, 2.0, 25.0))

    # electrode off the z=0 plane
    off = Electrode(id="O", pos_um=(0.0, 0.0, 5.0), shape="disk", size_um=10.0)
    with pytest.raises(ValueError, match="z=0"):
        M.validate_domain(M.FieldDomain(_array(off), HOMOG, 100.0, 60.0, 2.0, 25.0))

    # electrode reaches the outer boundary
    with pytest.raises(ValueError, match="outer"):
        M.validate_domain(M.FieldDomain(_array(_disk("A", 96, 0)), HOMOG, 100.0, 60.0, 2.0, 25.0))

    # bad mesh sizing (electrode coarser than far)
    with pytest.raises(ValueError, match="h_electrode"):
        M.validate_domain(M.FieldDomain(_array(_disk("A", 0, 0)), HOMOG, 100.0, 60.0, 30.0, 25.0))


def test_expected_footprint_centroid_and_area_per_shape():
    # disk/square/hex centred on pos; poly uses the area-weighted centroid
    sq = Electrode(id="S", pos_um=(7.0, 0.0, 0.0), shape="square", size_um=10.0)
    cx, cy, area = M._expected_footprint(sq)
    assert (cx, cy) == (7.0, 0.0) and area == pytest.approx(100.0)
    poly = Electrode(
        id="P",
        pos_um=(0.0, 0.0, 0.0),
        shape="poly",
        size_um=0.0,
        boundary_um=((0.0, 0.0, 0.0), (12.0, 0.0, 0.0), (0.0, 12.0, 0.0)),
    )
    pcx, pcy, parea = M._expected_footprint(poly)
    assert (pcx, pcy) == pytest.approx((4.0, 4.0))  # triangle centroid
    assert parea == pytest.approx(72.0)


def test_default_domain_encloses_the_array_and_sizes_the_mesh():
    arr = _array(_disk("A", -15, 0), _disk("B", 15, 0))
    dom = M.default_domain(arr, HOMOG)
    # domain comfortably contains both electrodes (center 15 + r 5 = 20)
    assert dom.half_width_um > 20.0
    # fine at the electrode, coarse far, and ordered
    assert 0 < dom.h_electrode_um <= dom.h_far_um
    # radius 5 / cells_per_radius 2.5 -> 2 um target at the electrode
    assert dom.h_electrode_um == pytest.approx(2.0)
    M.validate_domain(dom)  # self-consistent


def test_default_domain_depth_follows_the_layer_stack():
    cond = LayeredConductivity(
        layers=(
            Layer(sigma_S_per_m=1.0, thickness_um=40.0),
            Layer(sigma_S_per_m=0.3, thickness_um=60.0),
        )
    )
    dom = M.default_domain(_array(_disk("A", 0, 0)), cond)
    assert dom.depth_um == pytest.approx(100.0)
    assert [s.z1_um for s in M.layer_partition(dom)] == [40.0, 100.0]


def test_refined_scales_both_mesh_sizes():
    dom = M.default_domain(_array(_disk("A", 0, 0)), HOMOG)
    fine = dom.refined(2.0)
    assert fine.h_electrode_um == pytest.approx(dom.h_electrode_um / 2)
    assert fine.h_far_um == pytest.approx(dom.h_far_um / 2)
    # geometry unchanged
    assert (fine.half_width_um, fine.depth_um) == (dom.half_width_um, dom.depth_um)
    with pytest.raises(ValueError):
        dom.refined(0.0)


def test_tag_conventions_are_distinct():
    # ground / insulating / electrodes must not collide within the surface dim
    assert len({M.GROUND_TAG, M.INSULATING_TAG, M.ELECTRODE_TAG_BASE}) == 3
    assert M.ELECTRODE_TAG_BASE > M.INSULATING_TAG
    assert math.isfinite(M.LAYER_TAG_BASE)
