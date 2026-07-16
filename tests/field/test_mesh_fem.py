"""P4 S1 (fem): gmsh builds a tagged mesh that DOLFINx reads back correctly.

Confirms the mesh is not just written but *usable* by the backend: the physical
groups survive the round-trip into DOLFINx, and the tagged entities have the
right measure (electrode ~= pi r^2, the shell and layer volumes exact). This is
the contract P4 S2's DOLFINx backend builds on.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

import ufl  # noqa: E402
from dolfinx import fem  # noqa: E402
from dolfinx.io.gmsh import read_from_msh  # noqa: E402
from mpi4py import MPI  # noqa: E402

from engine.field import mesh as M  # noqa: E402
from engine.spec import (  # noqa: E402
    ElectrodeArray,
    HomogeneousConductivity,
    LayeredConductivity,
)
from engine.spec.conductivity import Layer  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem

R_UM = 5.0  # 10 um diameter disks throughout


def _two_electrode_array() -> ElectrodeArray:
    return ElectrodeArray(
        electrodes=(
            Electrode(id="A", pos_um=(-15.0, 0.0, 0.0), shape="disk", size_um=2 * R_UM),
            Electrode(id="B", pos_um=(15.0, 0.0, 0.0), shape="disk", size_um=2 * R_UM),
        )
    )


def _surface_area(msh, facet_tags, tag: int) -> float:
    ds = ufl.Measure("ds", domain=msh, subdomain_data=facet_tags)
    form = fem.form(fem.Constant(msh, 1.0) * ds(tag))
    return msh.comm.allreduce(fem.assemble_scalar(form), op=MPI.SUM)


def _volume(msh, cell_tags, tag: int) -> float:
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    form = fem.form(fem.Constant(msh, 1.0) * dx(tag))
    return msh.comm.allreduce(fem.assemble_scalar(form), op=MPI.SUM)


def test_homogeneous_mesh_tags_round_trip_through_dolfinx(tmp_path):
    arr = _two_electrode_array()
    dom = M.default_domain(arr, HomogeneousConductivity(sigma_S_per_m=1.0))
    out = str(tmp_path / "homog.msh")
    res = M.build_mesh(dom, out)

    assert set(res.electrode_tags) == {"A", "B"}
    assert res.layer_tags == (M.LAYER_TAG_BASE,)

    data = read_from_msh(out, MPI.COMM_WORLD, gdim=3)
    msh, cell_tags, facet_tags = data.mesh, data.cell_tags, data.facet_tags

    # every declared tag is present in the mesh DOLFINx read
    assert set(res.electrode_tags.values()) <= set(facet_tags.values.tolist())
    assert {res.ground_tag, res.insulating_tag} <= set(facet_tags.values.tolist())
    assert set(res.layer_tags) <= set(cell_tags.values.tolist())

    # electrode faces carry ~ pi r^2 (a meshed disk is faceted, so a few % under)
    for tag in res.electrode_tags.values():
        area = _surface_area(msh, facet_tags, tag)
        assert area == pytest.approx(math.pi * R_UM**2, rel=0.08)

    # the grounded shell = 4 sides + bottom, exact
    w, d = dom.half_width_um, dom.depth_um
    shell = 4 * (2 * w) * d + (2 * w) ** 2
    assert _surface_area(msh, facet_tags, res.ground_tag) == pytest.approx(shell, rel=1e-6)

    # the single layer fills the whole slab, exact
    assert _volume(msh, cell_tags, res.layer_tags[0]) == pytest.approx((2 * w) ** 2 * d, rel=1e-6)


def test_layered_mesh_splits_volume_by_layer(tmp_path):
    arr = _two_electrode_array()
    cond = LayeredConductivity(
        layers=(
            Layer(sigma_S_per_m=1.0, thickness_um=20.0),
            Layer(sigma_S_per_m=0.3, thickness_um=30.0),
            Layer(sigma_S_per_m=1.5, thickness_um=50.0),
        )
    )
    dom = M.FieldDomain(
        array=arr,
        conductivity=cond,
        half_width_um=200.0,
        depth_um=100.0,
        h_electrode_um=2.0,
        h_far_um=50.0,
    )
    out = str(tmp_path / "layered.msh")
    res = M.build_mesh(dom, out)
    assert len(res.layer_tags) == 3

    data = read_from_msh(out, MPI.COMM_WORLD, gdim=3)
    msh, cell_tags = data.mesh, data.cell_tags

    footprint = (2 * dom.half_width_um) ** 2
    expected = [footprint * t for t in (20.0, 30.0, 50.0)]
    for tag, exp in zip(res.layer_tags, expected, strict=True):
        assert _volume(msh, cell_tags, tag) == pytest.approx(exp, rel=1e-6)
