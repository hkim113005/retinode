# Electrode geometry: shapes, 3D bodies, arrays in tissue

This is the user-facing reference for the Phase-6 geometry model — how to describe
an electrode (2D shape, 3D body, or imported CAD), plant an array into the tissue,
and reason about how it interacts with the neuron population. It complements the
build plan in [phase-6-plan.md](phase-6-plan.md). For a task-oriented "just run it"
walkthrough, see the how-to in [custom-electrode.md](custom-electrode.md).

The one invariant to keep in mind: **geometry only changes the field solve.**
Every electrode — a flat disk, a penetrating pillar, an imported CAD solid — reaches
the cable model through the same transfer-matrix contract (`Ve = A @ I` at the
cell's compartments). The NEURON biophysics never sees the geometry, so anything
here is confined to the field/mesh layer. Shaped and 3D electrodes are **FEM-only**
(the analytical tier is a point source).

## The domain model

- **Coordinate convention.** `z = 0` is the array/substrate plane; **`+z` is into
  the tissue** (the electrode normal direction). The tissue, the electrode bodies,
  and any FEM-driven cell population all live at **`z ≥ 0`**. (The analytical tier
  is sign-agnostic — its field is mirror-symmetric across `z = 0` — so analytical-only
  scenes may use either sign; the FEM path requires `z ≥ 0`.)
- **The conductive domain is the tissue slab *minus* the electrode bodies.** A solid
  electrode is not part of the conductive medium: its **exposed conductive surface(s)**
  carry the current-injection Neumann flux (`I / conductive-area`), its **insulated
  surface(s)** (an insulated shank, the substrate) are zero-flux, and the tissue
  fills the rest. The FEM boolean-cuts each body out of the slab.
- **Neurons live only in the tissue.** A compartment cannot occupy an electrode body
  — that is a geometry conflict, resolved by the overlap policy below, never a field
  computed for a point inside metal.
- **The neuron is a passive probe.** The field is solved *without* the neuron present
  (the cell does not perturb it). This is the standard extracellular approximation;
  it degrades at **near-contact** (a membrane pressed against a conductive surface),
  which the overlap check flags.

## Describing an electrode

### 2D faces

An `Electrode` with no `body` is a flat face on the plane. `shape` ∈
`{"disk", "square", "hex", "poly"}` (`size_um` is the diameter / edge / flat-to-flat;
`poly` uses an explicit `boundary_um` outline):

```python
from engine.spec import Electrode
Electrode(id="d", pos_um=(0, 0, 0), shape="disk",   size_um=12)
Electrode(id="s", pos_um=(0, 0, 0), shape="square", size_um=12)
Electrode(id="p", pos_um=(0, 0, 0), shape="poly",   size_um=0,
          boundary_um=((-6,-6,0), (6,-6,0), (6,6,0), (-6,6,0)))
```

### 3D bodies

A `body` makes the electrode a solid protruding into the tissue. Three primitives,
each with a `conductive_faces` selector (`"tip"` / `"sides"` / `"all"`; a hemisphere
is always fully conductive):

```python
from engine.spec import Electrode, Hemisphere, Cylinder, Frustum
Electrode(id="h", pos_um=(0,0,0), shape="disk", size_um=0, body=Hemisphere(radius_um=10))
Electrode(id="c", pos_um=(0,0,0), shape="disk", size_um=0, body=Cylinder(radius_um=5, height_um=30))
Electrode(id="f", pos_um=(0,0,0), shape="disk", size_um=0,
          body=Frustum(base_radius_um=8, top_radius_um=2, height_um=20))  # a penetrating tip
```

The **hemisphere is the exact known-answer** geometry: on the insulating plane it
produces the point-source field `V = I / (2πσr)` for `r ≥ radius`, which the FEM
reproduces to a few percent — the anchor that makes the 3D field trustworthy.

### Imported CAD (STEP / BREP)

For a genuinely custom shape, load a STEP or BREP solid. `load_cad_body` reads it
once (gmsh), hashing its **content** (the geometric identity, for provenance) and
measuring the bounding box and exposed surface area. The CAD's origin is the
electrode's base on the array plane.

Like the primitives, an imported solid takes a `conductive_faces` selector (P6 S8):
the loader splits the exposed surface by depth into a deep **tip** and the lateral
**sides** (same 0.75·height threshold the mesh uses), so `"tip"` / `"sides"` /
`"all"` all work — not only the whole surface:

```python
from engine.field.mesh3d import load_cad_body   # needs the FEM env
from engine.spec import Electrode
body = load_cad_body("my_electrode.step", conductive_faces="sides")  # or "tip" / "all"
Electrode(id="cad", pos_um=(0, 0, 0), shape="disk", size_um=0, body=body)
```

**Accepted formats: STEP and BREP** (OpenCASCADE solids that boolean-cut cleanly).
STL is a surface tessellation, not a solid, and is not accepted — convert it to a
solid first, or use a primitive.

## Planting an array into tissue

An `ElectrodeArray` may mix flat and penetrating electrodes freely — one mesh cuts
every body and imprints every face. An `ArrayPlacement` poses the whole array with a
rigid **translation** and an optional **rotation/tilt**:

```python
from engine.spec import ElectrodeArray, ArrayPlacement
arr = ElectrodeArray(
    electrodes=(flat_disk, penetrating_pillar),
    placement=ArrayPlacement(
        offset_um=(100, 0, 0),        # position it over the tissue
        rotation_deg=(0, 15, 0),      # tilt 15° about y: pillars enter at an angle
    ),
)
```

`rotation_deg` rotates the whole array about its own origin (extrinsic x→y→z,
degrees) and then `offset_um` translates it — so a tilt makes penetrating electrodes
enter the tissue at an angle, with the electrode normals rotating to match. The FEM
mesh orients each body by the same rotation (built axis-aligned, then rotated and
translated) and classifies its tip/side faces in the **body-local frame**, so a
tilted pillar's tip is still its tip; the overlap check maps every query point
through the rotation's transpose into that local frame. The placement (offset **and**
rotation) is part of the array's content hash, so a re-posed array keys distinctly.

**Rotation is a FEM-tier concept.** The analytical tier is an orientation-free point
source (it sees only `pos_um`), so a tilted body must be solved with FEM. Flat 2D
faces are imprinted on the `z = 0` substrate plane; tilt is meant for 3D bodies (a
tilted flat disc is better modeled as a shallow body).

## Cell ↔ electrode overlap

Because an electrode body and a neuron cannot occupy the same space, `evaluate`
takes an `overlap_policy` that governs any cell a 3D body intersects. It runs the
same geometry check (`check_overlap`) the standalone helpers expose, but wired
straight into the population solve — the overlap indices are computed in the
NEURON model's own `segment_coords` order, so they line up exactly with the
transfer-matrix rows and the spike detectors:

```python
from engine.eval import evaluate
res = evaluate(patch, array, config, conductivity, overlap_policy="reject")    # default
res = evaluate(patch, array, config, conductivity, overlap_policy="displace")  # sever + score survivors
```

- **`reject`** (default) refuses a scene that puts a neuron inside metal — often the
  right answer, since for an epiretinal design a penetrating electrode hitting cells
  is usually a red flag, not a feature. It raises `OverlapConflict` naming the cell.
- **`displace`** models the electrode having displaced/severed the cell there: the
  interior compartments are **severed** — the field is never queried at them (an
  in-metal point that the FEM backend would reject) and no spike is detected there —
  and the cell is scored on its surviving compartments. The NEURON model itself is
  unchanged; only *which* compartments are driven and monitored changes.
- **near-contact** is flagged, not acted on: it marks where the passive-probe field
  approximation starts to fray (a compartment nearly touching the conductive metal).

The lower-level `check_overlap` / `resolve_overlap` helpers remain available for
inspecting a scene's conflicts directly (`resolve_overlap(report, "displace")`
returns `{cell: {compartments}}`); `evaluate` is the wired path that acts on them.

Overlap detection is exact for the primitives, and for an imported CAD body it is
exact to mesh resolution (P6 S9): `load_cad_body` bakes a coarse **triangulated
surface** into the `CadBody`, and the check does a pure-Python point-in-solid test
(ray parity) against it — no gmsh needed in the eval path. A `CadBody` with no baked
triangulation (e.g. hand-constructed) falls back to the conservative bounding
cylinder.

## Sweeping 3D designs

`ArrayGeometry` carries an optional `body`, so a geometry sweep can vary 3D
parameters the same way it varies flat layouts. `pillar_geometry_grid` enumerates
diameter × pitch × height as penetrating-cylinder arrays:

```python
from engine.study.geometry import pillar_geometry_grid
grid = pillar_geometry_grid(
    diameters_um=[8, 12], pitches_um=[30, 50], heights_um=[20, 40],
    arrangement="hex", aperture_um=120,
)
# feed `grid` to geometry_sweep / the surrogate exactly like a flat grid
```

The regime-aware backend selection routes these to FEM automatically.

## Validation and honest caveats

- **Validated** with the Phase-4 machinery: the hemisphere against its closed form;
  every 3D field for mesh convergence; DOLFINx vs NGSolve agreement on 3D and on a
  **placed mixed array** (all to a few percent); the CAD round-trip against the
  equivalent primitive (<1%).
- **FEM-only.** Shaped and 3D electrodes have no closed form in the analytical tier;
  the field for them must be FEM. Non-disk 2D may use analytical as a documented
  approximation.
- **Near-contact leaves the passive-probe regime.** A compartment within `ε` of a
  conductive surface is flagged because the standard model (field solved without the
  neuron) no longer holds there.
- **3D meshes are resolution- and truncation-sensitive.** Fine features (a sharp
  tip, a thin wall) need a fine mesh; check convergence, and keep the grounded shell
  a few electrode-spans away so truncation error stays below the feature you care
  about. Both matter *more* here than for a flat disk.
- **Array tilt/rotation** is supported (P6 S7): `ArrayPlacement.rotation_deg` poses
  the array at an angle; bodies orient in the FEM mesh and the overlap check follows.
  Analytical stays a point source, so tilt is FEM-only.
- **CAD face groups** are supported (P6 S8): an imported solid's `conductive_faces`
  selects tip / sides / all, split by centroid depth at load time. The split is a
  depth heuristic, not a semantic face-tagging — a genuinely branched electrode may
  need its groups defined in the CAD tool.
- **CAD overlap is exact to mesh resolution** (P6 S9): the check ray-casts against a
  baked triangulated surface, so it catches conflicts a bounding cylinder would miss
  (a square corner) and rejects points a bounding cylinder would over-flag (off to
  the side of a thin slab). Accuracy is set by the triangulation density chosen at
  load time.
- **The biophysics caveats are unchanged** — mouse RGC morphology, trend-not-magnitude
  validation (Phases 1/3). 3D geometry raises *field/placement* fidelity, not
  physiological fidelity: this is a hypothesis tester for electrode designs, not an
  absolute predictor.
