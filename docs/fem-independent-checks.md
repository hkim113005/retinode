# P4 S6: independent field checks (Sim4Life, COMSOL), deferred by design

**Status: documented, not built.** This is the one Phase-4 step scoped from the
start as "documented, not built" (phase-4-plan.md, D7 and the cut list), and it is
the first thing to drop under pressure. It is recorded here so that a future
implementer, once cloud or lab tooling exists, knows exactly what to build and how
it slots in, without re-deriving the design.

## Why deferred

Both are **commercial tools behind access we do not have during this work**:

- **Sim4Life**: a commercial full-wave and quasi-static EM solver, run in the
  cloud under license.
- **COMSOL**: a commercial multiphysics FEM package, typically a lab-seat license.

They were always intended as *independent third checks*, not load-bearing
validation. Phase 4's done-whens are already met without them:

- an open-source FEM field is **validated** (MMS, analytical half-space, two-layer
  closed form, current conservation, from P4 S2 and S3);
- it is **confirmed by a second backend** (DOLFINx agrees with NGSolve to
  sub-percent on the same mesh, P4 S5);
- the **analytical-vs-FEM regime is mapped** (P4 S5).

Sim4Life or COMSOL would add a *third, independent-implementation* cross-check
with a different mesher, solver, and vendor: valuable defense in depth, but
strictly a nice-to-have. Revisit when a Sim4Life cloud seat or a COMSOL lab
license is actually in hand.

## What makes them thin adapters (the reason deferral is cheap)

Every field solver in this project hides behind one contract
([`engine/field/backend.py`](../engine/field/backend.py)):

```python
class FieldBackend(Protocol):
    name: str
    def transfer_matrix(self, array, conductivity, query_points_um) -> np.ndarray: ...
```

`A[i, j]` is the extracellular potential at query point `i` per unit current on
electrode `j`, in **mV/µA**, so `Ve = A @ I`. Everything downstream (the cable
engine, the evaluator, the store) sees only `A`, never a solver. Adding a backend
means implementing that one method; nothing else in the system changes. The
**neutral geometry spec** (electrode primitives plus conductivity slabs,
[`engine/spec`](../engine/spec)) is what each backend meshes its own way, so the
geometry is defined once and shared.

## Sim4Life: a field-only import adapter

Sim4Life does not run in-process. It solves in the cloud and **exports a solved
field**, so the adapter is an *importer*, not a live solver:

1. **Export the geometry.** Write the neutral spec (electrode disks on z=0, the
   conductivity slabs) to a Sim4Life project, or reproduce it by hand in the GUI.
   One unit-current excitation per electrode.
2. **Solve in the cloud.** Sim4Life produces a solved potential field per
   excitation: a field file such as `.mat`, `.h5`, or an exported grid.
3. **Import into `A`.** A `Sim4LifeImport` backend reads the exported field,
   samples the potential at `query_points_um` (interpolating on Sim4Life's grid),
   scales to mV/µA, and returns `A` with one column per electrode excitation.
   `name = "sim4life_import"`.

Because it is a file-to-`A` importer, it needs **no Sim4Life dependency in the
codebase**, only a documented file format and an interpolating reader. It would be
`fem`-adjacent (or carry its own `sim4life` marker) and run only when a solved
file is present. The same MMS, analytical, and closed-form checks (P4 S2 and S3)
validate the import path: import a Sim4Life solve of a homogeneous half-space and
confirm it matches the analytical `A`.

## COMSOL: an adapter stub

COMSOL exposes a Java and Python API (`mph` / LiveLink) and can also export
fields. Two possible shapes, both thin:

- **Live adapter**: a `ComsolBackend` that drives a parametric COMSOL model
  through LiveLink, building the geometry from the neutral spec, solving one
  unit-current study per electrode, and extracting `Ve` at the query points into
  `A`.
- **Import adapter**: the same file-to-`A` pattern as Sim4Life, if only exported
  fields are available.

Left as a **documented interface**: the class name, the contract method it
satisfies, and the geometry it consumes. Not implemented until a lab seat exists.

## The gate for un-deferring this

Build the Sim4Life import first, because it has the lower friction: no live API,
just a file reader. Validate it against the analytical half-space exactly as the
DOLFINx backend was, then treat it as a third vote in the cross-check panel
alongside DOLFINx and NGSolve. COMSOL follows the same pattern if and when a
license appears. Neither blocks Phase 5.
