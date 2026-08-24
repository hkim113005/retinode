"""P6 S2 (fem): 3D electrode bodies mesh (tissue minus body), solve, and validate.

The hemisphere is the rigorous known-answer: a hemispherical electrode of radius a
on the insulating plane produces the point-source field V = I/(2 pi sigma r) for
r >= a (mV/uA: 1e3/(2 pi sigma r)). The cylinder validates that the conductive-face
selector actually shapes the field, and DOLFINx <-> NGSolve cross-checks the 3D
mesh."""

from __future__ import annotations

import math

import numpy as np
import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("gmsh")

from engine.field import mesh as M  # noqa: E402
from engine.field import mesh3d as M3  # noqa: E402
from engine.field.convergence import mesh_convergence  # noqa: E402
from engine.field.fem_fenicsx import (  # noqa: E402
    FenicsxBackend,
    _solve_on_mesh,
    solve_transfer_matrix,
)
from engine.spec import Cylinder, ElectrodeArray, Hemisphere, HomogeneousConductivity  # noqa: E402
from engine.spec.geometry import Electrode  # noqa: E402

pytestmark = pytest.mark.fem

SIGMA = HomogeneousConductivity(sigma_S_per_m=1.0)


def _hemisphere(radius_um: float) -> ElectrodeArray:
    e = Electrode(
        id="H",
        pos_um=(0.0, 0.0, 0.0),
        shape="disk",
        size_um=0.0,
        body=Hemisphere(radius_um=radius_um),
    )
    return ElectrodeArray(electrodes=(e,))


def test_hemisphere_field_matches_the_point_source_closed_form():
    arr = _hemisphere(10.0)
    # large domain so the grounded truncation is far from the sampled near field
    dom = M.FieldDomain(arr, SIGMA, 3000.0, 3000.0, 1.5, 300.0)
    zs = np.array([20.0, 30.0, 50.0])  # r = z on the axis, all >= radius
    q = np.column_stack([np.zeros_like(zs), np.zeros_like(zs), zs])

    a_fem = FenicsxBackend(domain=dom).transfer_matrix(arr, SIGMA, q)[:, 0]
    closed = np.array([1e3 / (2 * math.pi * 1.0 * z) for z in zs])
    rel = np.abs(a_fem - closed) / closed
    assert np.max(rel) < 0.05, f"hemisphere vs closed form max err {np.max(rel):.3f}"


def test_hemisphere_field_converges_under_refinement():
    arr = _hemisphere(10.0)
    base = M.FieldDomain(arr, SIGMA, 150.0, 150.0, 4.0, 40.0)
    q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 40.0]])
    rep = mesh_convergence(base, q, factors=(1.0, 2.0, 3.0), tol=0.05, degree=1)
    assert rep.levels[-1].rel_change < rep.levels[-2].rel_change  # tightening
    assert rep.converged


def test_cylinder_conductive_faces_shape_the_field():
    # a point below the pillar tip: injecting from the tip (deep, concentrated)
    # raises the potential there more than injecting from the sides (spread out).
    q = np.array([[0.0, 0.0, 45.0]])
    ve = {}
    for faces in ("tip", "sides"):
        e = Electrode(
            id="C",
            pos_um=(0.0, 0.0, 0.0),
            shape="disk",
            size_um=0.0,
            body=Cylinder(radius_um=5.0, height_um=30.0, conductive_faces=faces),
        )
        arr = ElectrodeArray(electrodes=(e,))
        dom = M.FieldDomain(arr, SIGMA, 1000.0, 1000.0, 2.0, 150.0)
        ve[faces] = solve_transfer_matrix(dom, q, degree=1)[0, 0]
    assert ve["tip"] > 0 and ve["sides"] > 0
    assert ve["tip"] > 1.2 * ve["sides"]  # the tip clearly concentrates the field deeper


def test_dolfinx_and_ngsolve_agree_on_a_3d_hemisphere_mesh(tmp_path):
    pytest.importorskip("ngsolve")
    from engine.field.fem_ngsolve import _solve_on_mesh_ngsolve

    arr = _hemisphere(10.0)
    dom = M.FieldDomain(arr, SIGMA, 500.0, 500.0, 2.0, 80.0)
    q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 40.0], [15.0, 0.0, 25.0]])
    result = M.build_mesh(dom, str(tmp_path / "hemi.msh"))  # one mesh, both solvers
    a_dolfinx = _solve_on_mesh(result, dom, q, 1)
    a_ngsolve = _solve_on_mesh_ngsolve(result, dom, q, 1)
    rel = np.abs(a_dolfinx - a_ngsolve) / np.abs(a_dolfinx)
    assert np.max(rel) < 0.03, f"3D solver disagreement {np.max(rel):.4f}"


def test_mixed_flat_and_penetrating_array_has_independent_columns():
    # P6 S3: a flat disk + a penetrating cylinder in one array mesh together.
    flat = Electrode(id="F", pos_um=(-40.0, 0.0, 0.0), shape="disk", size_um=12.0)
    cyl = Electrode(
        id="C",
        pos_um=(40.0, 0.0, 0.0),
        shape="disk",
        size_um=0.0,
        body=Cylinder(radius_um=5.0, height_um=30.0),
    )
    arr = ElectrodeArray(electrodes=(flat, cyl))
    dom = M.FieldDomain(arr, SIGMA, 400.0, 200.0, 3.0, 60.0)
    q = np.array([[-40.0, 0.0, 20.0], [40.0, 0.0, 45.0]])  # above the flat, below the tip
    a = solve_transfer_matrix(dom, q, degree=1)
    assert a.shape == (2, 2)
    assert a[0, 0] > a[0, 1]  # the point above the flat feels the flat electrode more
    assert a[1, 1] > a[1, 0]  # the point below the tip feels the cylinder more


def test_placement_offsets_the_field_rigidly():
    # a hemisphere planted at (100, 0) matches the same hemisphere at the origin,
    # sampled the same distance above -- placement is a rigid translation.
    from engine.spec import ArrayPlacement

    base = _hemisphere(10.0)
    placed = ElectrodeArray(
        electrodes=base.electrodes, placement=ArrayPlacement(offset_um=(100.0, 0.0, 0.0))
    )
    ve_placed = solve_transfer_matrix(
        M.FieldDomain(placed, SIGMA, 500.0, 500.0, 2.0, 80.0),
        np.array([[100.0, 0.0, 25.0]]),
        degree=1,
    )[0, 0]
    ve_ref = solve_transfer_matrix(
        M.FieldDomain(base, SIGMA, 500.0, 500.0, 2.0, 80.0),
        np.array([[0.0, 0.0, 25.0]]),
        degree=1,
    )[0, 0]
    assert ve_placed == pytest.approx(ve_ref, rel=0.02)


def test_tilted_hemisphere_field_is_rotation_invariant():
    # P6 S7: a hemisphere is a full sphere cut by the z>=0 tissue box; a sphere is
    # rotation-invariant, so the cut cavity (and the field) must be identical no
    # matter how the array is tilted. A strong known-answer that tilt doesn't
    # corrupt the field solve.
    from engine.spec import ArrayPlacement

    base = _hemisphere(10.0)
    tilted = ElectrodeArray(
        electrodes=base.electrodes, placement=ArrayPlacement(rotation_deg=(30.0, 20.0, 0.0))
    )
    q = np.array([[0.0, 0.0, 20.0], [0.0, 0.0, 40.0], [15.0, 0.0, 25.0]])
    a_base = solve_transfer_matrix(M.FieldDomain(base, SIGMA, 500.0, 500.0, 2.0, 80.0), q, degree=1)
    a_tilt = solve_transfer_matrix(
        M.FieldDomain(tilted, SIGMA, 500.0, 500.0, 2.0, 80.0), q, degree=1
    )
    rel = np.abs(a_tilt - a_base) / np.abs(a_base)
    assert np.max(rel) < 0.03, f"tilted hemisphere field drifted {np.max(rel):.4f}"


def test_tilted_cylinder_orients_its_tip_in_the_mesh():
    # P6 S7: a cylinder tilted 90 deg about y lays its axis along +x, so its deep
    # conductive tip moves from +z to +x. The field just beyond the tilted tip (+x)
    # must exceed the field at the old upright-tip location (+z), which proves the body is
    # actually oriented in the mesh, not just translated.
    from engine.spec import ArrayPlacement

    cyl = Electrode(
        id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=0.0,
        body=Cylinder(radius_um=5.0, height_um=30.0, conductive_faces="tip"),
    )
    tilted = ElectrodeArray(
        electrodes=(cyl,), placement=ArrayPlacement(rotation_deg=(0.0, 90.0, 0.0))
    )
    dom = M.FieldDomain(tilted, SIGMA, 400.0, 400.0, 2.0, 120.0)
    q = np.array([[35.0, 0.0, 0.0], [0.0, 0.0, 35.0]])  # beyond the tilted tip (+x) vs old tip (+z)
    a = solve_transfer_matrix(dom, q, degree=1)
    assert a[0, 0] > a[1, 0], "the tilted tip should dominate the field along +x, not +z"


_MM_PER_UM = 1.0e-3


def _write_step_cylinder(path: str, radius_um: float, height_um: float) -> None:
    """Write a STEP cylinder of the given MICRON size.

    gmsh/OCC stamps ``SI_UNIT(.MILLI.,.METRE.)`` into the STEP header, so the numbers
    written here are millimetres and must be scaled. This fixture previously wrote the
    micron values raw, which made the file claim a 5 mm electrode. That was harmless only
    because the loader also ignored the declared unit. Both halves are fixed now.
    """
    import gmsh

    gmsh.initialize()
    try:
        gmsh.model.add("cyl")
        gmsh.model.occ.addCylinder(
            0.0, 0.0, 0.0, 0.0, 0.0, height_um * _MM_PER_UM, radius_um * _MM_PER_UM
        )
        gmsh.model.occ.synchronize()
        gmsh.write(path)
    finally:
        gmsh.finalize()


def test_imported_cad_cylinder_reproduces_the_primitive_field(tmp_path):
    # P6 S5: a STEP solid loaded via load_cad_body meshes, solves, and matches the
    # equivalent parametric Cylinder -- the CAD import path is correct.
    from engine.field.mesh3d import load_cad_body

    step = str(tmp_path / "cyl.step")
    _write_step_cylinder(step, 5.0, 30.0)
    cad = load_cad_body(step)
    assert cad.bounding_radius_um == pytest.approx(5.0, abs=1e-3)
    assert cad.bounding_height_um == pytest.approx(30.0, abs=1e-3)
    # exposed area (side + tip, no z=0 base) matches the primitive cylinder "all"
    assert cad.surface_area_um2 == pytest.approx(2 * math.pi * 5 * 30 + math.pi * 25, rel=1e-3)

    q = np.array([[0.0, 0.0, 45.0], [10.0, 0.0, 15.0], [0.0, 0.0, 50.0]])  # outside the body
    cad_e = Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=0.0, body=cad)
    prim_e = Electrode(
        id="C",
        pos_um=(0.0, 0.0, 0.0),
        shape="disk",
        size_um=0.0,
        body=Cylinder(radius_um=5.0, height_um=30.0),
    )
    a_cad = solve_transfer_matrix(
        M.FieldDomain(ElectrodeArray((cad_e,)), SIGMA, 1000.0, 1000.0, 2.0, 150.0), q
    )[:, 0]
    a_prim = solve_transfer_matrix(
        M.FieldDomain(ElectrodeArray((prim_e,)), SIGMA, 1000.0, 1000.0, 2.0, 150.0), q
    )[:, 0]
    assert np.max(np.abs(a_cad - a_prim) / np.abs(a_prim)) < 0.03


def _write_step_slab(path: str, hx: float, hy: float, height: float) -> None:
    """Write a STEP slab of the given MICRON half-extents, scaled to millimetres,
    the unit gmsh/OCC stamps into the STEP header (see _write_step_cylinder)."""
    import gmsh

    hx, hy, height = hx * _MM_PER_UM, hy * _MM_PER_UM, height * _MM_PER_UM
    gmsh.initialize()
    try:
        gmsh.model.add("slab")
        gmsh.model.occ.addBox(-hx, -hy, 0.0, 2 * hx, 2 * hy, height)
        gmsh.model.occ.synchronize()
        gmsh.write(path)
    finally:
        gmsh.finalize()


def test_loaded_cad_overlap_is_exact_not_the_bounding_cylinder(tmp_path):
    # P6 S9: a wide thin slab (x half-extent 15, y half-extent 3). Its bounding
    # cylinder has radius 15, so a point 10 um off-axis in y is *inside* the cylinder
    # but well outside the actual slab. The baked triangulation excludes it exactly,
    # where the old bounding-cylinder test would over-flag it.
    from engine.field.mesh3d import load_cad_body
    from engine.spec.body import point_in_body

    slab = str(tmp_path / "slab.step")
    _write_step_slab(slab, 15.0, 3.0, 20.0)
    cad = load_cad_body(slab)
    assert cad.surface_tris, "the loader must bake a triangulated surface"
    assert cad.bounding_radius_um == pytest.approx(15.0, abs=1e-3)

    assert point_in_body(cad, 0.0, 0.0, 10.0)  # centre, inside
    assert point_in_body(cad, 14.0, 0.0, 10.0)  # near the +x end, inside the slab
    over = (0.0, 10.0, 10.0)  # rho=10 < bounding_radius 15, but |y|=10 > 3 -> outside
    assert not point_in_body(cad, *over)  # exact: correctly excluded


def test_cad_face_groups_split_and_shape_the_field(tmp_path):
    # P6 S8: the loader splits an imported solid's exposed area into a deep tip and
    # lateral sides, and conductive_faces selects which inject, so a "sides"-only
    # CAD electrode drives a different field than the fully-conductive "all".
    from engine.field.mesh3d import load_cad_body

    step = str(tmp_path / "cyl.step")
    _write_step_cylinder(step, 5.0, 30.0)

    cad_all = load_cad_body(step, conductive_faces="all")
    # the split matches the cylinder's analytic caps/walls
    assert cad_all.tip_area_um2 == pytest.approx(math.pi * 25, rel=1e-3)  # tip cap pi r^2
    assert cad_all.sides_area_um2 == pytest.approx(2 * math.pi * 5 * 30, rel=1e-3)  # wall
    assert cad_all.tip_area_um2 + cad_all.sides_area_um2 == pytest.approx(cad_all.surface_area_um2)

    cad_sides = load_cad_body(step, conductive_faces="sides")
    q = np.array([[0.0, 0.0, 45.0], [12.0, 0.0, 15.0]])  # beyond the tip vs beside the wall
    dom = lambda body: M.FieldDomain(  # noqa: E731
        ElectrodeArray((Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk",
                                  size_um=0.0, body=body),)),
        SIGMA, 1000.0, 1000.0, 2.0, 150.0,
    )
    a_all = solve_transfer_matrix(dom(cad_all), q)[:, 0]
    a_sides = solve_transfer_matrix(dom(cad_sides), q)[:, 0]
    # dropping the tip cap must weaken the field just beyond the tip, measurably
    assert a_sides[0] < a_all[0]
    assert np.max(np.abs(a_all - a_sides) / np.abs(a_all)) > 0.02


def test_dolfinx_and_ngsolve_agree_on_a_placed_mixed_3d_array(tmp_path):
    # P6 S6: the second-solver cross-check on a representative planted array:
    # a flat disk + a penetrating cylinder, translated into the tissue.
    pytest.importorskip("ngsolve")
    from engine.field.fem_ngsolve import _solve_on_mesh_ngsolve
    from engine.spec import ArrayPlacement

    flat = Electrode(id="F", pos_um=(-30.0, 0.0, 0.0), shape="disk", size_um=12.0)
    cyl = Electrode(id="C", pos_um=(30.0, 0.0, 0.0), shape="disk", size_um=0.0,
                    body=Cylinder(radius_um=5.0, height_um=25.0))
    arr = ElectrodeArray(
        electrodes=(flat, cyl), placement=ArrayPlacement(offset_um=(10.0, 5.0, 0.0))
    )
    dom = M.FieldDomain(arr, SIGMA, 400.0, 200.0, 3.0, 60.0)
    # query points near each planted electrode (placement shifts them +10,+5 in x,y)
    q = np.array([[-20.0, 5.0, 18.0], [40.0, 5.0, 40.0], [10.0, 5.0, 30.0]])
    result = M.build_mesh(dom, str(tmp_path / "placed_mixed.msh"))  # one mesh, both solvers
    a_dolfinx = _solve_on_mesh(result, dom, q, 1)
    a_ngsolve = _solve_on_mesh_ngsolve(result, dom, q, 1)
    assert a_dolfinx.shape == a_ngsolve.shape == (3, 2)
    rel = np.abs(a_dolfinx - a_ngsolve) / np.abs(a_dolfinx)
    assert np.max(rel) < 0.03, f"placed-array solver disagreement {np.max(rel):.4f}"


@pytest.mark.neuron
@pytest.mark.slow
def test_fem_3d_field_drives_a_real_neuron_population(neuron_h):
    """P6 end-to-end: a 3D electrode's FEM field drives a real RGC population to a
    selectivity result -- the full pipeline (3D geometry -> tissue-minus-body FEM
    field -> NEURON thresholds) in one environment. Requires both dolfinx and
    neuron, so it runs only in the FEM CI job."""
    from engine.eval import check_overlap, evaluate, resolve_overlap
    from engine.spec import RGC, RetinalPatch, StimConfig, Waveform

    cyl = Electrode(id="C", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=0.0,
                    body=Cylinder(radius_um=5.0, height_um=30.0))
    arr = ElectrodeArray(electrodes=(cyl,))
    # cells in the tissue (z >= 0), the target just past the pillar tip (z=30)
    patch = RetinalPatch(
        cells=(RGC(id="t", cell_type="parasol_on", soma_um=(18.0, 0.0, 40.0)),
               RGC(id="n1", cell_type="parasol_on", soma_um=(70.0, 0.0, 40.0))),
        target_id="t", optic_disc_um=(2000.0, 0.0, 40.0),
    )
    # the somata sit clear of the electrode metal (the S4 overlap guard is happy)
    somata = {c.id: [c.soma_um] for c in patch.cells}
    assert not check_overlap(arr, somata).has_conflict
    assert resolve_overlap(check_overlap(arr, somata), "reject") == {}

    dom = M.FieldDomain(arr, SIGMA, 1500.0, 500.0, 4.0, 200.0)  # contains the cells
    cfg = StimConfig.from_map({"C": -1.0}, waveform=Waveform(phase_width_us=200.0))
    res = evaluate(patch, arr, cfg, SIGMA, backend=FenicsxBackend(domain=dom))

    assert res.activated  # the FEM 3D field drove the target to threshold
    assert res.thresholds.target_threshold_uA is not None
    assert res.thresholds.target_threshold_uA > 0.0


# --- CAD units: a STEP declares its own, and it is almost never microns ------------


def _step_cylinder_mm(path, radius, height):
    """Write a STEP cylinder whose numbers are MILLIMETRES. gmsh/OCC stamps
    ``SI_UNIT(.MILLI.,.METRE.)`` into the header, as every CAD package does by
    default. That is the whole point of these two tests."""
    import gmsh

    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("c")
        gmsh.model.occ.addCylinder(0, 0, 0, 0, 0, height, radius)
        gmsh.model.occ.synchronize()
        gmsh.write(str(path))
    finally:
        gmsh.finalize()


def test_a_millimetre_step_is_converted_to_microns(tmp_path):
    """A solid drawn as 0.005 x 0.030 in a millimetre file IS a 5 x 30 um electrode.

    The raw coordinates used to be taken as microns, so this real design loaded as
    0.005 um: 1000x too small, silently, and it still produced a plausible-looking
    score. The declared unit is now honoured on import.
    """
    step = tmp_path / "real.step"
    _step_cylinder_mm(step, radius=0.005, height=0.030)
    body = M3.load_cad_body(str(step))
    assert body.bounding_radius_um == pytest.approx(5.0, rel=1e-3)
    assert body.bounding_height_um == pytest.approx(30.0, rel=1e-3)


def test_a_wrong_scale_cad_is_refused_rather_than_solved(tmp_path):
    """The other half: numbers that only make sense as microns, in a millimetre file,
    are a unit error. 5 x 30 mm is 10000 x 30000 um, not a retinal electrode. It used
    to load as 5 x 30 um and score as though nothing were wrong."""
    step = tmp_path / "wrong.step"
    _step_cylinder_mm(step, radius=5.0, height=30.0)  # 5 mm x 30 mm
    with pytest.raises(ValueError, match="declared length unit"):
        M3.load_cad_body(str(step))
