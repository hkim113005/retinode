# Phase 6 — Custom electrode geometry and 3D array placement in tissue

**Goal.** Extend the electrode model from flat disks pinned to the array plane to:

1. **Arbitrary 2D outlines** — square, polygon;
2. **True 3D electrode bodies** — parametric primitives (pillar, cylinder, frustum,
   recessed well, penetrating tip) and **imported CAD** (STEP/BREP);
3. **3D placement of whole arrays into tissue** — position, orientation, and
   per-electrode **insertion depth**, so an array of mixed flat and penetrating
   electrodes can be *planted* into the retina at a chosen pose and its interaction
   with the neuron population simulated;

all **behind the existing `FieldBackend` transfer-matrix contract**, so the cable /
NEURON biophysics is unchanged (a custom electrode changes only the mesh and which
surfaces inject current — verified: `engine/cable/` never references electrode
shape, size, or position).

**Done when** a user can (1) define a non-disk 2D electrode, a 3D primitive
electrode, and an imported CAD electrode; (2) assemble them into an array and
**place, orient, and insert** that array into the tissue at a chosen depth and
angle; (3) have the FEM solve the field in the **tissue-minus-electrode-bodies**
domain, with any **cell/electrode overlap** resolved by an explicit policy; and
(4) obtain a **validated** selectivity/safety score for the RGC population — with
the analytical-vs-FEM regime, the overlap policy, and the near-contact limit all
honestly reported.

**Why it matters.** The tool's founding purpose is to be a hypothesis tester for
electrode designs before fabrication. The richest hypotheses are not "rearrange
flat disks" but **"what if the electrode had a 3D shape, and what if the array were
planted into the tissue like *this*"** — penetrating tips that reach the target
layer, recessed wells that shape the near field, mixed surface/penetrating arrays,
tilted insertions. This phase is what makes the tool a genuine 3D design-space
explorer. It is a **geometry/field** capability: it raises the fidelity of the
*field* and the *placement*, while the biophysical caveats (mouse RGC morphology,
trend-not-magnitude validation) carry over unchanged from Phases 1/3 and stay
honestly flagged.

---

## The domain model (read first)

This is the conceptual core the rest of the plan builds on: how electrode bodies,
tissue, and neurons coexist.

**Coordinate convention (to be pinned and reconciled).** The array/substrate plane
is `z = 0`; **tissue fills `z ≥ 0`** (increasing `z` is depth into the retina);
electrodes sit at `z = 0` (flush) or **protrude / penetrate into `z > 0`**; the RGC
population is placed **in the tissue (`z ≥ 0`)**. *Today these conventions are
inconsistent:* the analytical backend is sign-agnostic (pure distance + an image
across `z=0`) and existing patches place somata at `z < 0`, while the FEM mesh
builds its tissue slab at `0 ≤ z ≤ depth`. The analytical path masks this because
it works either way; the FEM path does not. **Reconciling to one convention —
electrodes, tissue, and cells on the same side of the plane — is a foundational
step (P6 S3), not a detail**, because "planting an array into tissue" is
meaningless until the tissue and the cells are on the same side as the electrodes.

**The conductive domain is tissue *minus* the electrode bodies.** A physical
electrode is solid; tissue (and neurons) cannot occupy its volume. So the FEM
domain is the tissue slab with every electrode body **boolean-subtracted** out
(gmsh OCC `fragment`/`cut`). The electrodes are *not* part of the conductive
medium. On each electrode:

- its **exposed conductive surface(s)** carry the current-injection **Neumann flux**
  (`I / conductive-area`) — generalizing the disk's flat face to a 3D surface;
- its **insulated surface(s)** (an insulated shank, the substrate) are **zero-flux**;
- the **tissue fills everything else**, and that is where the field is solved.

**Neurons live only in the tissue.** A compartment cannot be inside an electrode
body — that is a **geometry conflict**, not a field to compute (see the overlap
policy, P6 S4). The interesting, well-posed regime is a 3D electrode *near* cells
(a tip reaching close to a soma, a shank beside an axon of passage) without
intersecting them — cleanly handled, because the transfer matrix samples the field
at compartment coordinates that lie in the tissue.

**The neuron is a passive probe.** As throughout the project, the extracellular
field is solved **without** the neuron present (the cell does not back-perturb the
field), and reaches the cable model as `Ve = A @ I` at each compartment. This is
the standard extracellular-stimulation approximation; it is valid when the cell is
small relative to source distances and **degrades at near-contact** (a membrane
pressed against a conductive surface reshapes the local field). P6 S4 flags
near-contact rather than silently trusting it. **NEURON is unchanged** — every 3D
electrode, array pose, and CAD import affects only *what `A` is*.

---

## Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Behind the contract | **No change to `FieldBackend.transfer_matrix` or the cable/NEURON layer.** Geometry, placement, and overlap all live in the field/mesh/spec layers; the biophysics consumes `Ve` unchanged. |
| D2 | CAD & mesh path | **gmsh OpenCASCADE.** 2D via occ primitives/wires; 3D via occ 3D primitives and `occ.importShapes` (STEP/BREP), boolean-**subtracted** from the tissue slab. No new meshing dependency. |
| D3 | Additive spec | Extend `engine/spec` **without breaking existing disk specs**. Reuse `square`/`poly` for 2D; add an optional **`ElectrodeBody`** (3D primitive params or CAD reference + conductive-surface selection) on an electrode (`body=None` ⇒ today's flat disk), and an **`ArrayPlacement`** (rigid pose + per-electrode insertion) for planting the whole array. Hashing/serialization stay stable and **extend the P4 S4 content-addressed keys** (a CAD file's content hash + the placement pose are part of `field_key`). |
| D4 | FEM-only for shaped/3D | The analytical tier is a point/disk source and **cannot** represent a shaped or 3D electrode or a subtracted domain; backend selection (P5 D2) routes shaped/3D geometries to FEM. Non-disk **2D** may still use analytical as a *documented approximation*. |
| D5 | Boundary conditions | **Neumann flux on the conductive surface(s)** (`I / conductive-area`); **zero-flux on insulated surfaces**; grounded far-field truncation (as Phase 4). A convention marks which surfaces of a primitive/CAD solid are conductive. |
| D6 | Validated like Phase 4 | Reuse the Phase-4 machinery: **known-answer** (small-electrode disk limit; hemispherical electrode closed form), **mesh convergence** (P4 S4), **DOLFINx–NGSolve agreement** (P4 S5). No 3D number ships without convergence + a second-solver check. |
| D7 | CAD scope | **STEP/BREP in, STL deferred.** OCC imports STEP/BREP *solids* (boolean-subtractable); STL is a surface tessellation, not a solid — support via a documented solidification step or defer. Formats pinned explicitly. |
| D8 | Domain = tissue − electrodes | The conductive domain is the tissue slab with all electrode bodies subtracted, on **one pinned depth convention** (tissue `z ≥ 0`, electrodes at/into `z > 0`, cells in `z ≥ 0`). Reconciling the analytical/FEM/placement conventions is P6 S3. |
| D9 | Cell↔electrode overlap policy | A compartment inside an electrode body is a **conflict**, resolved explicitly, never silently: **default `reject`** (report the conflict and refuse the scene); **opt-in `displace`** (deactivate the compartments inside the body, modeling insertion damage/displacement). **Near-contact** (a compartment within `ε` of a conductive surface) is **flagged** as leaving the passive-probe regime. |

---

## Module layout

```
engine/spec/
  geometry.py        + ElectrodeBody (3D primitive | CAD ref + conductive faces)     [P6 S2]
  placement.py       + ArrayPlacement (rigid pose + per-electrode insertion depth)    [P6 S3]
engine/field/
  mesh.py            generalize the 2D imprint (disk -> square/polygon)              [P6 S1]
  mesh3d.py          3D electrode bodies + array pose: build, subtract, tag surfaces  [P6 S2-S3]
engine/eval/
  overlap.py         cell/electrode overlap detection + reject/displace + near-contact [done]
  safety.py          + conductive-surface area for 3D electrodes (2D already handled)  [P6 S2]
engine/study/
  geometry.py        + generators for 3D arrays and insertion configurations          [P6 S5]
docs/
  electrode-geometry.md   the domain model, overlap policy, conventions, caveats       [done]
```

---

## Ordered steps

- **P6 S1 — Arbitrary 2D shapes in the FEM mesh — done.** `mesh.py` imprints
  **square / hex / polygon** faces (OCC plane surfaces from
  `engine.spec.geometry.electrode_outline`), and the electrode-surface matching is
  now a per-shape centroid + area test (`_expected_footprint`); the disk-only guard
  in `validate_domain` is lifted (it accepts disk/square/hex/poly and rejects a
  polygon with no outline). `electrode_area_um2` + `electrode_outline` moved to
  `spec/geometry.py` as the **single source of truth** shared by the mesh and the
  safety charge-density check (`safety.py` re-imports it). Verified: each shape
  meshes with its **exact** area through DOLFINx (square/hex/poly to <1e-4;
  the faceted disk ~4% under), and a **square electrode solves** with its far field
  agreeing with the analytical point source (<10%). Fast tests cover the outlines,
  areas, footprints, and validation; `fem` tests cover the meshed areas and the
  square solve.

- **P6 S2 — 3D electrode body (single electrode) — done.** `spec/body.py` adds
  **`ElectrodeBody`** primitives — `Hemisphere`, `Cylinder`, `Frustum`, each with a
  `conductive_faces` selector (`tip`/`sides`/`all`) — attached to an electrode via
  an additive `body` field (`None` ⇒ today's flat face; the multi-arm union
  serializes and content-addresses). `radius_um` and `electrode_area_um2` defer to
  the body (the conductive-surface area flows straight into `safety.py`'s 3D charge
  density). `field/mesh3d.py` builds each body in OCC and classifies its cavity
  walls; `build_mesh` now **dispatches**: flat electrodes imprint faces (P4/S1),
  body electrodes are **boolean-cut from the tissue** and their walls split into
  conductive (Neumann flux) vs insulated (zero-flux, an insulated shank) — one
  shared tagging/sizing tail. Mixed flat+3D arrays raise `NotImplementedError`
  (P6 S3). **Validated (`test_mesh3d_fem.py`, fem):** a hemispherical electrode
  reproduces the exact point-source closed form `V = I/(2πσr)` to **1–3.5%** (the
  hemisphere *is* the equipotential source, so uniform-flux = equipotential here);
  the field **converges** under refinement; a cylinder's **tip vs sides** selector
  measurably reshapes the field (tip concentrates it ~1.7× deeper); and
  **DOLFINx ≈ NGSolve** on the 3D mesh to <3%.

- **P6 S3 — 3D array placement & mixed arrays — done.** `build_mesh` now assembles
  **any mix of flat and penetrating electrodes in one build**: the unified
  `_build_electrode_surfaces` cuts every 3D body from the tissue *and* imprints
  every flat face, then classifies the boundary (flat faces + substrate → top;
  cavity walls → 3D electrodes; shell → ground) — the S2 mixed-array
  `NotImplementedError` is gone. **`ArrayPlacement`** (a rigid **translation**) is
  added to `ElectrodeArray`; `apply_placement` poses the whole array (positions and
  polygon outlines) and, being part of the array's hash, keys a re-posed array
  distinctly (provenance). The **coordinate convention (D8) is pinned**: `z = 0`
  array plane, `+z` into the tissue, and the tissue / electrode bodies / any
  FEM-driven cell population all at `z ≥ 0` (the analytical tier stays
  sign-agnostic — its field is mirror-symmetric across `z = 0`). Validated
  (`test_mesh3d_fem.py`, fem): a **mixed flat + penetrating** array has independent
  columns (a point above the disk feels the disk; below the pillar tip feels the
  pillar); a hemisphere **planted at an offset** reproduces the origin field
  rigidly (<2%). **Array tilt/rotation is deferred** — it repositions the substrate
  plane itself (a larger change), documented on `ArrayPlacement`; the realistic
  epiretinal case (array parallel to the surface, electrodes penetrating
  perpendicular) is covered by translation + per-electrode bodies.

- **P6 S4 — Cell↔electrode interaction & overlap policy — done.** The physical
  fact — a neuron cannot occupy the metal — made concrete as **pure geometry**.
  `spec/body.py` gained `point_in_body` (the exact analytic counterpart of the OCC
  solid the mesh cuts, so the check and the mesh can't disagree about where the
  metal is) and `surface_distance_um` (signed SDF, exact for hemisphere/cylinder,
  approximate frustum). `eval/overlap.py`: `check_overlap(array, cell_compartments,
  eps)` flags every compartment **inside** a body (a conflict) or within `eps` of a
  surface (**near-contact** — where the passive-probe field approximation frays),
  applying the array placement first so bodies are tested at their planted
  positions. `resolve_overlap(report, policy)` applies **D9**: **`reject`** raises
  `OverlapConflict` naming the cell/electrode/compartment; **`displace`** returns
  `{cell: {compartments to deactivate}}` — the interior compartments the caller
  drops, the survivors still simulated (no NEURON-model change, only *which*
  compartments run). Validated (fast, `test_overlap.py` + `test_body.py`): a cell
  whose compartments fall inside a penetrating pillar is detected and rejected;
  `displace` reports exactly the interior compartments; a compartment 1 µm off the
  wall flags near-contact but not conflict; a comfortable gap flags nothing; a
  flat-only array never conflicts; placement moves the body before the check. **The
  evaluator consumes `resolve_overlap`'s decision** (drop the flagged compartments,
  or refuse the scene) — a thin integration point, since the biophysics is untouched.

- **P6 S5 — CAD import + provenance + sweep integration — done.** A `CadBody` spec
  references a **STEP/BREP** solid; `load_cad_body` (gmsh) reads it once and stores
  the geometric summaries — the **file content hash** (the geometric identity),
  bounding radius/height, and the exposed surface area — so the pure-spec helpers
  (`radius_um`, `electrode_area_um2`, overlap via a conservative bounding cylinder)
  need no gmsh, and the whole exposed surface conducts. `mesh3d.add_body_solid`
  imports the solid via `occ.importShapes` and translates it to the electrode's
  planted position; the rest of the mixed-array build (P6 S3) is unchanged.
  **Round-trip validated:** a STEP cylinder reproduces the equivalent parametric
  `Cylinder` field to **<1%** (bounding radius/height and exposed area match to
  1e-3). **Provenance:** because `content_hash` is a `CadBody` field, `spec_hash` →
  `field_key` distinguishes two different CAD files automatically (tested) — no
  design's field is silently reused for another (extends P4 S4). **3D sweeps:**
  `ArrayGeometry` gained an optional `body`, so `build_array` attaches it to every
  electrode, and `pillar_geometry_grid` enumerates diameter × pitch × **height** as
  penetrating-cylinder arrays — so `geometry_sweep` + the surrogate explore 3D
  insertion designs exactly like flat layouts, routed to FEM by backend selection
  (P5 D2). Face-group selection on imported CAD (tip/sides) and array tilt remain
  the documented extensions.

- **P6 S6 — Cross-check, regime, and docs — done.** The second-solver cross-check
  is extended to a **representative planted array**: DOLFINx ≈ NGSolve to **<3%** on
  a placed **mixed** array (a flat disk + a penetrating cylinder, translated into
  the tissue), read from one mesh (`test_mesh3d_fem.py`, `fem`). The user-facing
  reference [electrode-geometry.md](electrode-geometry.md) documents the domain
  model (tissue − electrodes), the coordinate convention, how to describe each
  electrode kind (2D shape / 3D body / imported CAD), planting an array, the
  **overlap policy**, sweeping 3D designs, the accepted CAD formats (STEP/BREP; STL
  out), and the honest caveats (FEM-only; near-contact leaves the passive-probe
  regime; 3D mesh resolution + truncation sensitivity; the deferred extensions).
  **Phase 6 complete.**

---

## Spec additions (concrete shape)

Additive to `engine/spec`, existing disk specs unchanged:

- **`ElectrodeBody`** (optional, on an `Electrode`; `None` ⇒ flat disk today):
  - *primitive*: base 2D shape + `height_um` + optional `taper` + a
    `conductive_faces` selector (e.g. `"tip"`, `"sides"`, `"all"`, `"top"`);
  - *or CAD*: a `cad_path` (STEP/BREP) + `conductive_faces` selector (named group or
    predicate) + a local origin.
- **`ArrayPlacement`** (optional, on an `ElectrodeArray`; `None` ⇒ flush at `z=0`):
  - `translation_um` + `rotation` (the array plane's pose in tissue coordinates), and
  - per-electrode `insertion_depth_um` (how far each electrode's body reaches into
    `z > 0`; `0` = flush) — enabling **mixed flat + penetrating arrays**.
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
- **`fem`:** 2D polygon solve + convergence + small-limit analytical agreement; 3D
  primitive solve + hemispherical known-answer + convergence + NGSolve agreement; a
  **placed 3D array** (mixed flat + penetrating) solves with independent columns;
  CAD-import round-trip vs the primitive; a small 3D-insertion geometry sweep to a
  frontier.
- **`neuron`:** one end-to-end — a **placed 3D array driving a real RGC population**
  to thresholds/selectivity, exercising the overlap policy (a cell near / into an
  electrode: `reject` refuses, `displace` drops interior compartments and the rest
  still fire).

---

## Validation & honesty

- **Known-answer / convergence / second-solver** as Phase 4 — no 3D number without
  them.
- The **overlap policy is explicit and reported**, never silent; a scene that puts a
  neuron inside metal fails loudly (or displaces, by opt-in), it does not compute a
  meaningless field.
- **Near-contact is flagged** as leaving the passive-probe regime — the one place the
  standard model frays, called out rather than trusted.
- **3D is FEM-only**; analytical remains a 2D-only approximation with its documented
  error.
- The **biophysics caveats are unchanged** (mouse RGC morphology, trend-not-magnitude)
  — 3D geometry raises field/placement fidelity, not physiological fidelity.

---

## What to cut under pressure, in order

Drop **CAD import + sweep integration (S5)** first — parametric 3D primitives with
`ArrayPlacement` already cover the testable design space and need no external files.
Then drop the **`displace` policy** (keep `reject` — the honest default). Then drop
the **near-contact flag** (document the limit instead). **Never cut:** the 2D
generalization (S1), the 3D primitive **mesh + solve + validation** (S2), **array
placement/insertion** (S3), or **overlap detection + reject** (S4) — that quartet is
"define a 3D array, plant it into tissue, and see how it interacts with the
neurons," which is the whole point of the request.

---

## Compute

3D and multi-electrode subtracted meshes with fine features are markedly heavier
than the planar disk case, so **mesh convergence** (P4 S4), the **cost estimate**
(P5 D5), and the **analytical-vs-FEM regime** (P4 S5) all apply and matter *more*.
Local for development; escalate large 3D sweeps per
[compute-adapters.md](compute-adapters.md).

## Dependencies

Phase 6 needs **Phase 4** (the FEM backend + MMS/convergence/agreement machinery)
and reuses **Phase 5** (the geometry sweep, provenance, surrogate). It should land
**before the geometry study** (Phase 8 in the renumbered roadmap), which will want
to compare 3D designs — the 3D array-in-tissue capability is precisely what makes
that study's design finding novel.
