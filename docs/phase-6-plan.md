# Phase 6: custom electrode geometry and 3D array placement in tissue

**Goal.** Extend the electrode model from flat disks pinned to the array plane to:

1. **Arbitrary 2D outlines:** square, polygon;
2. **True 3D electrode bodies:** parametric primitives (pillar, cylinder, frustum,
   recessed well, penetrating tip) and **imported CAD** (STEP/BREP);
3. **3D placement of whole arrays into tissue:** position, orientation, and
   per-electrode **insertion depth**, so an array of mixed flat and penetrating
   electrodes can be *planted* into the retina at a chosen pose and its interaction
   with the neuron population simulated;

all **behind the existing `FieldBackend` transfer-matrix contract**, so the cable
and NEURON biophysics is unchanged. A custom electrode changes only the mesh and
which surfaces inject current, and this is verified: `engine/cable/` never
references electrode shape, size, or position.

**Done when** a user can (1) define a non-disk 2D electrode, a 3D primitive
electrode, and an imported CAD electrode; (2) assemble them into an array and
**place, orient, and insert** that array into the tissue at a chosen depth and
angle; (3) have the FEM solve the field in the **tissue-minus-electrode-bodies**
domain, with any **cell/electrode overlap** resolved by an explicit policy; and
(4) obtain a **validated** selectivity and safety score for the RGC population,
with the analytical-vs-FEM regime, the overlap policy, and the near-contact limit
all honestly reported.

**Why it matters.** The tool's founding purpose is to test hypotheses about
electrode designs before fabrication. The richest hypotheses are not "rearrange
flat disks" but **"what if the electrode had a 3D shape, and what if the array were
planted into the tissue like *this*"**: penetrating tips that reach the target
layer, recessed wells that shape the near field, mixed surface and penetrating
arrays, tilted insertions. This phase is what makes the tool a genuine 3D
design-space explorer. It is a **geometry and field** capability, so it raises the
fidelity of the *field* and the *placement* while the biophysical caveats (mouse
RGC morphology, trend-not-magnitude validation) carry over unchanged from Phases
1 and 3 and stay honestly flagged.

---

## The domain model (read first)

This is the conceptual core the rest of the plan builds on: how electrode bodies,
tissue, and neurons coexist.

**Coordinate convention (to be pinned and reconciled).** The array/substrate plane
is `z = 0`; **tissue fills `z ≥ 0`** (increasing `z` is depth into the retina);
electrodes sit at `z = 0` (flush) or **protrude or penetrate into `z > 0`**; the
RGC population is placed **in the tissue (`z ≥ 0`)**. *Today these conventions are
inconsistent:* the analytical backend is sign-agnostic (pure distance plus an image
across `z=0`) and existing patches place somata at `z < 0`, while the FEM mesh
builds its tissue slab at `0 ≤ z ≤ depth`. The analytical path masks this because
it works either way; the FEM path does not. **Reconciling to one convention, with
electrodes, tissue, and cells on the same side of the plane, is a foundational
step (P6 S3), not a detail**, because "planting an array into tissue" is
meaningless until the tissue and the cells are on the same side as the electrodes.

**The conductive domain is tissue *minus* the electrode bodies.** A physical
electrode is solid; tissue (and neurons) cannot occupy its volume. So the FEM
domain is the tissue slab with every electrode body **boolean-subtracted** out
(gmsh OCC `fragment`/`cut`). The electrodes are *not* part of the conductive
medium. On each electrode:

- its **exposed conductive surface(s)** carry the current-injection **Neumann flux**
  (`I / conductive-area`), generalizing the disk's flat face to a 3D surface;
- its **insulated surface(s)** (an insulated shank, the substrate) are **zero-flux**;
- the **tissue fills everything else**, and that is where the field is solved.

**Neurons live only in the tissue.** A compartment cannot be inside an electrode
body. That is a **geometry conflict**, not a field to compute (see the overlap
policy, P6 S4). The interesting, well-posed regime is a 3D electrode *near* cells
without intersecting them: a tip reaching close to a soma, a shank beside an axon
of passage. That case is handled cleanly, because the transfer matrix samples the
field at compartment coordinates that lie in the tissue.

**The neuron is a passive probe.** As throughout the project, the extracellular
field is solved **without** the neuron present (the cell does not back-perturb the
field), and reaches the cable model as `Ve = A @ I` at each compartment. This is
the standard extracellular-stimulation approximation; it is valid when the cell is
small relative to source distances and **degrades at near-contact**, because a
membrane pressed against a conductive surface reshapes the local field. P6 S4
flags near-contact rather than silently trusting it. **NEURON is unchanged:** every
3D electrode, array pose, and CAD import affects only *what `A` is*.

---

## Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Behind the contract | **No change to `FieldBackend.transfer_matrix` or the cable/NEURON layer.** Geometry, placement, and overlap all live in the field/mesh/spec layers; the biophysics consumes `Ve` unchanged. |
| D2 | CAD & mesh path | **gmsh OpenCASCADE.** 2D via occ primitives/wires; 3D via occ 3D primitives and `occ.importShapes` (STEP/BREP), boolean-**subtracted** from the tissue slab. No new meshing dependency. |
| D3 | Additive spec | Extend `engine/spec` **without breaking existing disk specs**. Reuse `square`/`poly` for 2D; add an optional **`ElectrodeBody`** (3D primitive params or a CAD reference, plus conductive-surface selection) on an electrode (`body=None` ⇒ today's flat disk), and an **`ArrayPlacement`** (rigid pose plus per-electrode insertion) for planting the whole array. Hashing and serialization stay stable and **extend the P4 S4 content-addressed keys**: a CAD file's content hash and the placement pose are both part of `field_key`. |
| D4 | FEM-only for shaped/3D | The analytical tier is a point source and **cannot** represent a shaped or 3D electrode, or a subtracted domain; backend selection (P5 D2) routes shaped and 3D geometries to FEM. Non-disk **2D** may still use analytical as a *documented approximation*. |
| D5 | Boundary conditions | **Neumann flux on the conductive surface(s)** (`I / conductive-area`); **zero-flux on insulated surfaces**; grounded far-field truncation (as Phase 4). A convention marks which surfaces of a primitive/CAD solid are conductive. |
| D6 | Validated like Phase 4 | Reuse the Phase-4 machinery: **known-answer** checks (the small-electrode disk limit; the hemispherical-electrode closed form), **mesh convergence** (P4 S4), and **DOLFINx–NGSolve agreement** (P4 S5). No 3D number ships without convergence and a second-solver check. |
| D7 | CAD scope | **STEP/BREP in, STL deferred.** OCC imports STEP/BREP *solids*, which are boolean-subtractable. STL is a surface tessellation, not a solid, so it needs a documented solidification step or a deferral. Formats are pinned explicitly. |
| D8 | Domain = tissue − electrodes | The conductive domain is the tissue slab with all electrode bodies subtracted, on **one pinned depth convention** (tissue `z ≥ 0`, electrodes at/into `z > 0`, cells in `z ≥ 0`). Reconciling the analytical/FEM/placement conventions is P6 S3. |
| D9 | Cell↔electrode overlap policy | A compartment inside an electrode body is a **conflict**, resolved explicitly and never silently: **default `reject`** (report the conflict and refuse the scene); **opt-in `displace`** (deactivate the compartments inside the body, modeling insertion damage or displacement). **Near-contact**, a compartment within `ε` of a conductive surface, is **flagged** as leaving the passive-probe regime. |

---

## Module layout

```
engine/spec/
  geometry.py        + ElectrodeBody (3D primitive | CAD ref + conductive faces)    [P6 S2]
  placement.py       + ArrayPlacement (rigid pose + per-electrode insertion depth)   [P6 S3]
engine/field/
  mesh.py            generalize the 2D imprint (disk -> square/polygon)              [P6 S1]
  mesh3d.py          3D bodies + array pose: build, subtract, tag surfaces           [P6 S2-S3]
engine/eval/
  overlap.py         overlap detection + reject/displace + near-contact              [done]
  safety.py          + conductive-surface area for 3D electrodes                     [P6 S2]
engine/study/
  geometry.py        + generators for 3D arrays and insertion configurations         [P6 S5]
docs/
  electrode-geometry.md   the domain model, overlap policy, conventions, caveats     [done]
```

---

## Ordered steps

- **P6 S1: Arbitrary 2D shapes in the FEM mesh. Done.** `mesh.py` imprints
  **square / hex / polygon** faces (OCC plane surfaces from
  `engine.spec.geometry.electrode_outline`), and the electrode-surface matching is
  now a per-shape centroid + area test (`_expected_footprint`); the disk-only guard
  in `validate_domain` is lifted (it accepts disk/square/hex/poly and rejects a
  polygon with no outline). `electrode_area_um2` + `electrode_outline` moved to
  `spec/geometry.py` as the **single source of truth** shared by the mesh and the
  safety charge-density check (`safety.py` re-imports it). Verified: each
  shape meshes with its **exact** area through DOLFINx (square, hex, and polygon to
  <1e-4; the faceted disk ~4% under), and a **square electrode solves** with its far
  field agreeing with the analytical point source to <10%. Fast tests cover the
  outlines, areas, footprints, and validation; `fem` tests cover the meshed areas
  and the square solve.

- **P6 S2: 3D electrode body (single electrode). Done.** `spec/body.py` adds
  **`ElectrodeBody`** primitives, `Hemisphere`, `Cylinder`, and `Frustum`, each
  with a `conductive_faces` selector (`tip`/`sides`/`all`), attached to an electrode
  via an additive `body` field (`None` ⇒ today's flat face; the multi-arm union
  serializes and content-addresses). `radius_um` and `electrode_area_um2` defer to
  the body, so the conductive-surface area flows straight into `safety.py`'s 3D
  charge density. `field/mesh3d.py` builds each body in OCC and classifies its
  cavity walls, and `build_mesh` now **dispatches**: flat electrodes imprint faces
  (P4 S1), while body electrodes are **boolean-cut from the tissue** and their
  walls split into conductive (Neumann flux) and insulated (zero-flux, an insulated
  shank), sharing one tagging and sizing tail. Mixed flat and 3D arrays raise
  `NotImplementedError` (P6 S3). **Validated (`test_mesh3d_fem.py`, fem):** a
  hemispherical electrode reproduces the exact point-source closed form
  `V = I/(2πσr)` to **1–3.5%**, because the hemisphere *is* the equipotential
  source, so uniform flux and equipotential coincide here; the field **converges**
  under refinement; a cylinder's **tip versus sides** selector measurably reshapes
  the field, with the tip concentrating it ~1.7× deeper; and **DOLFINx ≈ NGSolve**
  on the 3D mesh to <3%.

- **P6 S3: 3D array placement and mixed arrays. Done.** `build_mesh` now assembles
  **any mix of flat and penetrating electrodes in one build**: the unified
  `_build_electrode_surfaces` cuts every 3D body from the tissue *and* imprints
  every flat face, then classifies the boundary (flat faces and substrate → top;
  cavity walls → 3D electrodes; shell → ground). The S2 mixed-array
  `NotImplementedError` is gone. **`ArrayPlacement`**, a rigid **translation**, is
  added to `ElectrodeArray`; `apply_placement` poses the whole array (positions and
  polygon outlines) and, being part of the array's hash, keys a re-posed array
  distinctly for provenance. The **coordinate convention (D8) is pinned**: a `z = 0`
  array plane, `+z` into the tissue, and the tissue, electrode bodies, and any
  FEM-driven cell population all at `z ≥ 0`. The analytical tier stays
  sign-agnostic, since its field is mirror-symmetric across `z = 0`. Validated
  (`test_mesh3d_fem.py`, fem): a **mixed flat and penetrating** array has
  independent columns (a point above the disk feels the disk, a point below the
  pillar tip feels the pillar), and a hemisphere **planted at an offset**
  reproduces the origin field rigidly (<2%). **Array tilt and rotation are
  deferred** because they reposition the substrate plane itself, a larger change,
  documented on `ArrayPlacement`. The realistic epiretinal case, an array parallel
  to the surface with electrodes penetrating perpendicular, is covered by
  translation plus per-electrode bodies. *(S7 below closes this deferral.)*

- **P6 S4: Cell↔electrode interaction and overlap policy. Done.** One physical
  fact, that a neuron cannot occupy the metal, made concrete as **pure geometry**.
  `spec/body.py` gained `point_in_body` (the exact analytic counterpart of the OCC
  solid the mesh cuts, so the check and the mesh cannot disagree about where the
  metal is) and `surface_distance_um` (a signed SDF, exact for the hemisphere and
  cylinder, approximate for the frustum). In `eval/overlap.py`,
  `check_overlap(array, cell_compartments, eps)` flags every compartment **inside**
  a body (a conflict) or within `eps` of a surface (**near-contact**, where the
  passive-probe field approximation frays), applying the array placement first so
  bodies are tested at their planted positions. `resolve_overlap(report, policy)`
  applies **D9**: **`reject`** raises `OverlapConflict` naming the cell, electrode,
  and compartment; **`displace`** returns `{cell: {compartments to deactivate}}`,
  the interior compartments the caller drops, with the survivors still simulated.
  Nothing in the NEURON model changes, only *which* compartments run. Validated
  (fast, `test_overlap.py` and `test_body.py`): a cell whose compartments fall
  inside a penetrating pillar is detected and rejected; `displace` reports exactly
  the interior compartments; a compartment 1 µm off the wall flags near-contact but
  not conflict; a comfortable gap flags nothing; a flat-only array never conflicts;
  and placement moves the body before the check. **The evaluator consumes
  `resolve_overlap`'s decision**, dropping the flagged compartments or refusing the
  scene: a thin integration point, since the biophysics is untouched.

- **P6 S5: CAD import, provenance, and sweep integration. Done.** A `CadBody` spec
  references a **STEP/BREP** solid. `load_cad_body` (gmsh) reads it once and stores
  the geometric summaries: the **file content hash** (the geometric identity), the
  bounding radius and height, and the exposed surface area. The pure-spec helpers
  (`radius_um`, `electrode_area_um2`, and overlap via a conservative bounding
  cylinder) therefore need no gmsh, and the whole exposed surface conducts.
  `mesh3d.add_body_solid` imports the solid via `occ.importShapes` and translates it
  to the electrode's planted position; the rest of the mixed-array build (P6 S3) is
  unchanged. **Round-trip validated:** a STEP cylinder reproduces the equivalent
  parametric `Cylinder` field to **<1%**, with bounding radius, height, and exposed
  area matching to 1e-3. **Provenance:** because `content_hash` is a `CadBody`
  field, `spec_hash` → `field_key` distinguishes two different CAD files
  automatically (tested), so no design's field is silently reused for another. That
  extends P4 S4. **3D sweeps:** `ArrayGeometry` gained an optional `body`, so
  `build_array` attaches it to every electrode, and `pillar_geometry_grid`
  enumerates diameter × pitch × **height** as penetrating-cylinder arrays. Both
  `geometry_sweep` and the surrogate therefore explore 3D insertion designs exactly
  like flat layouts, routed to FEM by backend selection (P5 D2). Face-group
  selection on imported CAD (tip or sides) and array tilt remain documented
  extensions. *(S8 and S7 below close both.)*

- **P6 S6: Cross-check, regime, and docs. Done.** The second-solver cross-check
  is extended to a **representative planted array**: DOLFINx ≈ NGSolve to **<3%** on
  a placed **mixed** array (a flat disk plus a penetrating cylinder, translated into
  the tissue), read from one mesh (`test_mesh3d_fem.py`, `fem`). The user-facing
  reference [electrode-geometry.md](electrode-geometry.md) documents the domain
  model (tissue minus electrodes), the coordinate convention, how to describe each
  electrode kind (2D shape, 3D body, or imported CAD), planting an array, the
  **overlap policy**, sweeping 3D designs, the accepted CAD formats (STEP/BREP in,
  STL out), and the honest caveats: FEM-only; near-contact leaves the passive-probe
  regime; 3D mesh resolution and truncation sensitivity; the deferred extensions.
  **Phase 6 (core) complete.**

### Extensions (formerly deferred)

- **P6 S7: Array tilt and rotation. Done.** `ArrayPlacement` gains `rotation_deg`
  (extrinsic x→y→z about the array origin, applied before `offset_um`). A pure
  rotation matrix (`spec/geometry.py`) drives it everywhere. `apply_placement`
  rotates each position, polygon outline, and electrode normal; the FEM mesh builds
  each body axis-aligned at the origin, then `occ.rotate`s it into the pose and
  translates it (`mesh3d.add_body_solid`); cavity-wall tip and side classification
  happens in the **body-local frame** (`R^T`·centroid), so a tilted pillar's tip is
  still its tip; and the overlap check maps every query point through `R^T` into the
  local frame before the `point_in_body` test. Validated by unit tests (rotation
  math, posed positions, normals and outlines, overlap under a 90° tilt) and by FEM:
  a **tilted hemisphere is field-invariant** (a sphere cut by the z≥0 box is
  identical under rotation, a tight known answer) and a **tilted cylinder orients
  its tip in the mesh** (the field dominates along the laid-over axis, not the old
  one). Rotation is FEM-tier, because the analytical point source is
  orientation-free (documented).

- **P6 S8: CAD face-group selection. Done.** An imported solid is no longer forced
  to `conductive_faces="all"`. `load_cad_body` splits the exposed surface (the z=0
  base excluded) into a deep **tip** and lateral **sides** by centroid depth, using
  the same 0.75·height threshold `classify_cavity_surfaces` uses on the cavity
  walls, so the load-time group areas match the meshed conductive surfaces. It
  stores `tip_area_um2` and `sides_area_um2` on `CadBody`, and both
  `body_conductive_area_um2` and the mesh classifier honour the selector. Validated
  by unit tests (per-group conductive area by selector) and by FEM: a cylinder STEP
  splits into a `π r²` tip and `2π r h` sides, and a **sides-only** CAD electrode
  drives a measurably weaker field beyond the tip than the fully-conductive **all**.
  The split is a documented depth heuristic, not semantic face-tagging.

- **P6 S9: Exact CAD overlap. Done.** The overlap check for an imported solid used
  to be a conservative bounding cylinder, which both over- and under-flags a
  non-cylindrical CAD. Now `load_cad_body` bakes a coarse **triangulated surface**
  (the whole closed solid, in the body-local frame) into `CadBody`, and
  `point_in_body` and `surface_distance_um` do a pure-Python **point-in-solid** test
  (ray parity, Möller–Trumbore with a skewed ray to dodge edge and vertex
  degeneracies) plus a closest-point-to-triangle signed distance. There is **no gmsh
  in the eval path**, so overlap stays a uv-env concern. An empty triangulation
  falls back to the bounding cylinder. Validated by unit tests (a square pillar's
  corner is caught where the bounding cylinder misses it; signed-distance sign and
  magnitude; serialization round-trip of the baked mesh) and by FEM: a **loaded
  wide-slab STEP** correctly excludes an off-axis point the bounding cylinder would
  over-flag. Accuracy is set by the load-time triangulation density.

**Phase 6 complete: core (S1–S6) and all three extensions (S7–S9).**

---

## Spec additions (concrete shape)

Additive to `engine/spec`, existing disk specs unchanged:

- **`ElectrodeBody`** (optional, on an `Electrode`; `None` ⇒ flat disk today):
  - *primitive*: a base 2D shape, `height_um`, an optional `taper`, and a
    `conductive_faces` selector (for example `"tip"`, `"sides"`, `"all"`, `"top"`);
  - *or CAD*: a `cad_path` (STEP/BREP), a `conductive_faces` selector (named group or
    predicate), and a local origin.
- **`ArrayPlacement`** (optional, on an `ElectrodeArray`; `None` ⇒ flush at `z=0`):
  - `translation_um` and `rotation` (the array plane's pose in tissue coordinates),
    and
  - per-electrode `insertion_depth_um`, how far each electrode's body reaches into
    `z > 0` (`0` = flush), which is what enables **mixed flat and penetrating
    arrays**.
- **Overlap policy** enum on the scene/evaluator: `reject` (default) | `displace`,
  plus a `near_contact_eps_um` threshold.

Hashing/serialization for all three round-trip and **content-address distinctly**
(two designs → two keys), extending the P4 S4 `field_key`/`result_key` provenance.

---

## Testing strategy

- **Fast (no solve):** `ElectrodeBody` / `ArrayPlacement` / overlap-policy specs
  round-trip and content-address distinctly; the 2D shape geometry (vertices, area);
  **overlap detection as a pure geometry predicate** (a point inside/outside a
  primitive body under a placement); the `reject`/`displace` policy logic; the
  conductive-surface-area arithmetic for safety.
- **`fem`:** a 2D polygon solve plus convergence plus small-limit analytical
  agreement; a 3D primitive solve plus the hemispherical known answer plus
  convergence plus NGSolve agreement; a **placed 3D array** (mixed flat and
  penetrating) solving with independent columns; a CAD-import round trip against the
  primitive; and a small 3D-insertion geometry sweep to a frontier.
- **`neuron`:** the **full pipeline in one environment**. A 3D electrode's FEM
  field drives a **real RGC population** to a threshold and selectivity result
  (`evaluate(..., backend=FenicsxBackend(...))`), with the S4 overlap guard checked
  on the placed somata. This runs in the **FEM CI job**, which now installs
  `neuron` alongside dolfinx and compiles its mechanisms on first use. It closes the
  one gap the conda/uv env split had left untested: 3D geometry → tissue-minus-body
  FEM field → NEURON population → score, end to end.
- **`neuron` (overlap policy, wired):** `evaluate`'s `overlap_policy` is exercised
  against a penetrating body that swallows the target's soma. `reject` raises
  `OverlapConflict`. `displace` **severs** the interior compartments, so the field
  is never queried there (the property the FEM backend needs, since an in-metal
  point raises) and no spike is detected there, yet the cell still reaches threshold
  on its survivors. This is the policy running through the real cable solve, not
  just a report (`tests/cable/test_displace.py`).

---

## Validation & honesty

- **Known answer, convergence, second solver**, exactly as in Phase 4. No 3D number
  ships without them.
- The **overlap policy is explicit and reported**, never silent. A scene that puts a
  neuron inside metal fails loudly, or displaces by opt-in. It does not compute a
  meaningless field.
- **Near-contact is flagged** as leaving the passive-probe regime: the one place the
  standard model frays, called out rather than trusted.
- **3D is FEM-only.** Analytical remains a 2D-only approximation with its documented
  error.
- The **biophysics caveats are unchanged** (mouse RGC morphology,
  trend-not-magnitude). 3D geometry raises field and placement fidelity, not
  physiological fidelity.

---

## What to cut under pressure, in order

Drop **CAD import and sweep integration (S5)** first, because parametric 3D
primitives with `ArrayPlacement` already cover the testable design space and need no
external files. Then drop the **`displace` policy**, keeping `reject`, the honest
default. Then drop the **near-contact flag** and document the limit instead.
**Never cut:** the 2D generalization (S1), the 3D primitive **mesh, solve, and
validation** (S2), **array placement and insertion** (S3), or **overlap detection
plus reject** (S4). That quartet is "define a 3D array, plant it into tissue, and
see how it interacts with the neurons," which is the whole point of the request.

---

## Compute

3D and multi-electrode subtracted meshes with fine features are markedly heavier
than the planar disk case, so **mesh convergence** (P4 S4), the **cost estimate**
(P5 D5), and the **analytical-vs-FEM regime** (P4 S5) all apply and matter *more*.
Develop locally; escalate large 3D sweeps per
[compute-adapters.md](compute-adapters.md).

## Dependencies

Phase 6 needs **Phase 4** (the FEM backend plus the MMS, convergence, and
agreement machinery) and reuses **Phase 5** (the geometry sweep, provenance, and
surrogate). It should land **before the geometry study** (Phase 8 in the renumbered
roadmap), which will want to compare 3D designs. The 3D array-in-tissue capability
is precisely what makes that study's design finding novel.
