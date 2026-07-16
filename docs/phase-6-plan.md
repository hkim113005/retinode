# Phase 6 — Electrode geometry: arbitrary 2D shapes and 3D CAD models

**Goal.** Extend the electrode geometry representation and the FEM meshing from
planar disks to **(a) arbitrary 2D outlines** (square, polygon) and **(b) true 3D
electrode bodies** — parametric 3D primitives (pillars, wells, frustums) and
**imported CAD** (STEP/BREP) — all **behind the existing `FieldBackend`
transfer-matrix contract**, so the cable engine, evaluator, sweep, Pareto reducer,
and surrogate are unchanged. This turns the tool from a planar-disk array
comparator into a **design-space explorer for genuinely novel 3D electrode
geometry**, testable before fabrication.

**Done when** a user can define a non-disk 2D electrode and a 3D electrode (both a
parametric primitive and an imported CAD solid), the FEM backend meshes and solves
each — **validated** by the Phase-4 machinery (known-answer / convergence /
second-solver agreement) — and it flows through the evaluator and the geometry
sweep to a selectivity/safety score, with the analytical-vs-FEM regime honestly
flagged (**shaped and 3D electrodes are FEM-only**).

**Why it matters.** The tool's founding purpose is to be a *hypothesis tester for
electrode designs before real experiments*. The highest-value hypotheses are about
**3D structure** — protrusions, recessed wells, textured or patterned surfaces,
non-planar returns — which a planar disk simply cannot represent. This is the
capability that makes the tool answer *"what if the electrode looked like **this**"*
rather than only *"what if we rearranged disks."* It is a **geometry/field**
capability: it raises the fidelity of the *field*, while the biophysical caveats
(mouse RGC morphology, trend-not-magnitude validation) carry over unchanged from
Phases 1/3 and are still honestly flagged.

## Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Behind the contract | **No change to `FieldBackend.transfer_matrix`.** A custom electrode changes only the *mesh* and *which surfaces carry the Neumann flux*; the cable/eval/sweep/Pareto/surrogate stack is untouched. This is the Phase-4 pattern (a new backend dropped in behind the contract) applied to geometry. |
| D2 | CAD path | **gmsh OpenCASCADE.** Reuse the existing gmsh/occ pipeline (`engine/field/mesh.py`). 2D shapes via occ primitives/wires; 3D via occ 3D primitives and `occ.importShapes` (STEP/BREP), boolean-**fragmented** into the tissue slab. No new meshing dependency. |
| D3 | Additive spec | Extend `engine/spec/geometry.py` **without breaking existing disk specs**. Reuse the `poly`/`square` members already in the `Shape` literal for 2D; add a **3D electrode representation** (parametric primitive params, and/or a CAD-file reference + placement). Hashing/serialization stay stable and **extend the P4 S4 content-addressed keys** — a CAD file's content hash + placement is part of `field_key`, so designs never key-collide. |
| D4 | FEM-only for shaped/3D | The analytical tier is a point/disk source and **cannot** represent a shaped or 3D electrode; backend selection (P5 D2) routes shaped/3D electrodes to FEM. Non-disk 2D may still use analytical as a **documented approximation**. |
| D5 | Flux on the conductive surface(s) | Current injection is a Neumann flux (`I / conductive-area`) over the electrode's **exposed conductive surface(s)**; insulated faces (shank, substrate) are zero-flux. This generalizes the disk's flat-face BC to 3D bodies. A convention marks which surfaces of an imported solid are conductive. |
| D6 | Validated like Phase 4 | Every capability reuses the Phase-4 validation: **MMS / analytical agreement** where a closed form exists (the small-electrode disk limit; a hemispherical electrode), **mesh convergence** (P4 S4), and **DOLFINx–NGSolve agreement** on the 3D mesh (P4 S5). No 3D number ships without convergence + a second-solver check. |
| D7 | CAD scope | **STEP/BREP in, STL deferred.** gmsh occ natively imports STEP/BREP *solids* (boolean-fragmentable). STL is a surface tessellation, not a solid — support via a documented solidification step or defer. The accepted formats are pinned explicitly. |

## Module layout

```
engine/spec/
  geometry.py        + Electrode3D / CAD-reference representation (additive)        [P6 S2]
engine/field/
  mesh.py            generalize the 2D imprint (disk -> square/polygon)            [P6 S1]
  mesh3d.py          3D electrode bodies: primitives + CAD import, fragment, tag   [P6 S2-S3]
engine/study/
  geometry.py        + generators for shaped / 3D electrode arrays and patterns    [P6 S4]
docs/
  electrode-geometry.md   the geometry model, conductive-surface convention, caveats [P6 S5]
```

## Ordered steps

- **P6 S1 — Arbitrary 2D shapes in the FEM mesh.** Generalize `mesh.py`'s disk
  imprint to **square and polygon** (occ rectangle / plane-surface-from-wire), and
  generalize the electrode-surface matching (currently `area ≈ πr²`) to a per-shape
  area/centroid test. Lift the disk-only guard in `validate_domain`. Validate: a
  polygon electrode's field **converges**, and in the small-electrode limit
  **agrees with the analytical** point source; a square vs its inscribed disk shows
  the expected near-field difference. Reuses P4 convergence + agreement.
- **P6 S2 — 3D electrode primitives.** Extend the spec with a **parametric 3D
  electrode** (base shape + height + taper + which surface is conductive → pillar /
  cylinder / frustum / recessed well). Build it in occ, boolean-**fragment** it into
  the tissue slab, and **tag the conductive surface(s)** for the flux BC (insulated
  faces zero-flux). Solve + validate against a **known-answer 3D case** (a
  hemispherical electrode's closed form) plus convergence + NGSolve agreement.
- **P6 S3 — CAD import (STEP/BREP).** `occ.importShapes` a user CAD solid,
  **place/orient** it in the domain (position, rotation), fragment into the tissue,
  and **tag its conductive surface(s)** by a selection convention (a named face
  group carried in the CAD, or a geometric predicate). Validate a **round-trip**: a
  CAD cylinder reproduces the P6 S2 primitive-cylinder field within tolerance.
- **P6 S4 — Provenance + sweep integration.** Extend `field_key`/hashing so
  shaped/3D geometries — including a **CAD file's content hash + placement** — are
  content-addressed, so no design's field is silently reused for another (extends
  P4 S4). Add study **generators/factories** for shaped and 3D electrode arrays and
  patterns, so `geometry_sweep` + the surrogate can sweep over **3D configurations**
  (spacing, height, taper, pattern). Backend selection (P5 D2) routes them to FEM.
- **P6 S5 — Cross-check, regime, and docs.** NGSolve agreement on a representative
  3D mesh; document the geometry model, the conductive-surface convention, the
  accepted CAD formats, and the honest accuracy caveats (FEM-only; mesh-resolution
  and truncation sensitivity for fine 3D features). `electrode-geometry.md` is the
  user-facing reference.

## Testing strategy

- **Fast (no solve):** the new spec types + hashing/serialization round-trip and
  content-address **distinctly** (two designs → two keys); the 2D shape geometry
  (vertices, area) and the 3D primitive parameterization; the study generators for
  shaped/3D arrays.
- **`fem`:** 2D polygon solve + convergence + small-limit analytical agreement; 3D
  primitive solve + known-answer + convergence + NGSolve agreement; CAD-import
  round-trip vs the primitive; a small shaped/3D geometry sweep to a frontier.

## What to cut under pressure, in order

Drop **CAD/STEP import (S3)** first — parametric 3D primitives (pillars / wells /
frustums) already cover most testable "patterns and configurations," and they need
no external files. Then drop the **sweep/surrogate integration (S4 generators)** — a
hand-built 3D array still evaluates end-to-end. **Never cut** the 2D generalization
(S1) or the 3D primitive **mesh + solve + validation** (S2): that is the core
capability, and the whole point of the request.

## Compute note

3D meshes with fine electrode features are heavier than the planar disk case, so
**mesh convergence** (P4 S4), the **cost estimate** (P5 D5), and the
**analytical-vs-FEM regime** (P4 S5) all apply and matter *more* here. Local for
development; escalate large 3D sweeps per [compute-adapters.md](compute-adapters.md).

## Dependencies

Phase 6 needs **Phase 4** (the FEM backend + MMS/convergence/agreement machinery)
and reuses **Phase 5** (the geometry sweep, provenance, and surrogate). It should
land **before the real geometry study** (Phase 8 in the renumbered roadmap), which
will want to compare 3D designs — the 3D electrode capability is precisely what
makes that study's design finding novel.
