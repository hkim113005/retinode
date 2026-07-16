# Electrode geometry: shapes, 3D bodies, arrays in tissue

This is the user-facing reference for the Phase-6 geometry model — how to describe
an electrode (2D shape, 3D body, or imported CAD), plant an array into the tissue,
and reason about how it interacts with the neuron population. It complements the
build plan in [phase-6-plan.md](phase-6-plan.md).

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
electrode's base on the array plane; the whole exposed surface conducts.

```python
from engine.field.mesh3d import load_cad_body   # needs the FEM env
from engine.spec import Electrode
body = load_cad_body("my_electrode.step")
Electrode(id="cad", pos_um=(0, 0, 0), shape="disk", size_um=0, body=body)
```

**Accepted formats: STEP and BREP** (OpenCASCADE solids that boolean-cut cleanly).
STL is a surface tessellation, not a solid, and is not accepted — convert it to a
solid first, or use a primitive.

## Planting an array into tissue

An `ElectrodeArray` may mix flat and penetrating electrodes freely — one mesh cuts
every body and imprints every face. An `ArrayPlacement` poses the whole array with
a rigid **translation**:

```python
from engine.spec import ElectrodeArray, ArrayPlacement
arr = ElectrodeArray(
    electrodes=(flat_disk, penetrating_pillar),
    placement=ArrayPlacement(offset_um=(100, 0, 0)),   # position it over the tissue
)
```

The placement is part of the array's content hash, so a re-posed array keys
distinctly for provenance. **Array tilt/rotation is deferred** — it repositions the
substrate plane itself. The realistic epiretinal case (array parallel to the
surface, electrodes penetrating perpendicular) is covered by translation + each
electrode's body.

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

Overlap detection is exact for the primitives; for a CAD body it uses a conservative
**bounding cylinder** (it over-flags rather than misses).

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
- **Deferred, documented extensions:** array tilt/rotation (moves the substrate
  plane); face-group selection on imported CAD (tip/sides on an arbitrary solid);
  exact CAD overlap (currently a bounding-cylinder approximation).
- **The biophysics caveats are unchanged** — mouse RGC morphology, trend-not-magnitude
  validation (Phases 1/3). 3D geometry raises *field/placement* fidelity, not
  physiological fidelity: this is a hypothesis tester for electrode designs, not an
  absolute predictor.
