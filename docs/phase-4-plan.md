# Phase 4 — FEM accuracy layer: plan

**Goal.** A validated, drop-in open-source **FEM field backend** behind the
existing transfer-matrix contract, confirmed against known-answer solutions and a
second solver, and **extended to layered conductivity** — the retina's structure
the analytical backend rejects (`UnsupportedByBackend`) — with mesh-convergence
evidence per result and a map of where the analytical tier can be trusted.

**Done when** an open-source FEM field is validated and swappable behind the
contract, confirmed by a second backend, and the analytical-vs-FEM regime is
mapped. (Master plan: heavier work, suited to lab compute.)

**Why it matters beyond FEM:** this is where the two items deferred from P1/P3 get
their validation — **absolute threshold magnitudes** and **Fan 2019's full somatic
selectivity gain** — because both need a faithful *layered* field, not the
homogeneous half-space.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Primary FEM backend | **FEniCSx / DOLFINx** (per master plan), behind the `FieldBackend.transfer_matrix` contract. |
| D2 | Validation | **Method of Manufactured Solutions + analytical** (rigorous known-answer) as the primary correctness gate; **NGSolve** as the second-solver agreement check (the "confirmed by a second backend" done-when). |
| D3 | CI | **A dedicated FEM CI job** (micromamba installs DOLFINx + gmsh) runs `fem`-marked tests on every push. |
| D4 | Toolchain | FEniCSx has **no macOS/pip wheel** → the FEM env is **conda-forge (micromamba)**, *separate from uv*. The uv toolchain is untouched; a `fem`-marked, conda-only layer sits beside it. |
| D5 | Value-add scope | Layered conductivity is **in scope** (the whole point of FEM); homogeneous is validated first as the known-answer case. |
| D6 | Mesh | **gmsh** as the shared mesh front-end (neutral geometry → mesh both solvers read). |
| D7 | Boundary | Phase 4 is the **backend + validation**, not the sweep at scale (parametric FEM, surrogate, cluster/cloud = P5). Sim4Life/COMSOL are field-only/stub, documented/deferred. |

## Toolchain note (read first)

FEniCSx-first means the FEM layer cannot live in the uv environment. Plan:

- `env/fem-environment.yml` — a conda-forge env (`fenics-dolfinx`, `gmsh`,
  `python`, `numpy`, `pytest`) for local FEM dev and CI.
- The FEM CI job uses `mamba-org/setup-micromamba` to build that env, installs
  the project into it (`pip install -e . --no-deps` so `engine` imports work),
  and runs `pytest -m fem`. The existing `test`/`test-neuron` jobs are unchanged.
- **P4 S1 opens with a feasibility gate:** confirm DOLFINx installs (osx-arm64 +
  linux) and solves a trivial Poisson problem. If it cannot be made to install
  cleanly, fall back to NGSolve-first (D1 flips) before building anything on it.

## Module layout

```
engine/field/
  backend.py       transfer-matrix contract + UnsupportedByBackend             [done]
  analytical.py    Tier-1 analytical backend                                    [done]
  mesh.py          neutral geometry -> gmsh mesh (electrode surfaces + layers)  [P4 S1]
  fem_fenicsx.py   DOLFINx backend behind the contract                          [P4 S2-S3]
  fem_ngsolve.py   NGSolve backend (second-solver cross-check)                  [P4 S5]
  convergence.py   mesh-refinement convergence check                           [P4 S4]
env/
  fem-environment.yml   conda-forge FEM env (dolfinx, gmsh)                     [P4 S1]
.github/workflows/ci.yml   + a `fem` job (micromamba)                          [P4 S1]
```

## Ordered steps

- **P4 S1 — Toolchain, feasibility gate, and mesh.** Stand up the conda FEM env
  and the micromamba CI job; **verify DOLFINx solves a trivial Poisson problem**
  (the gate). Build `mesh.py`: a neutral parametric geometry — disk electrodes on
  the z=0 boundary over a tissue slab with optional conductivity layers — meshed
  by gmsh and refinable. Electrode boundary condition pinned: **current injection
  is a Neumann flux on each electrode surface**, insulating (zero-flux) elsewhere
  on the top boundary, with a truncated far-field / grounded outer boundary.
- **P4 S2 — DOLFINx backend (homogeneous) + MMS/analytical.** `transfer_matrix`
  via DOLFINx: one unit-current solve per electrode, Ve sampled at the query
  points → `A` (mV/µA, sign chain preserved). Validate with (a) **MMS** — impose a
  known analytic potential, recover it to mesh tolerance — and (b) **analytical
  agreement** — homogeneous half-space FEM `A` ≈ analytical `A` within tolerance.
- **P4 S3 — Layered conductivity (the value-add).** Extend the backend to
  `LayeredConductivity`. Validate against the **two-layer half-space closed form**
  (image series) and/or an MMS with a discontinuous σ across the layer interface.
- **P4 S4 — Convergence + provenance.** Refine the mesh until Ve (or the target
  metric) changes < tolerance between refinements; store the convergence curve so
  the claim is auditable. Thread mesh parameters + backend name into `field_key`
  (already backend-aware) so FEM results are cache-keyed and never silently reused
  across meshes.
- **P4 S5 — Second-solver agreement + regime map.** An NGSolve backend (pip,
  universal2) solving the **same gmsh mesh**; assert DOLFINx ≈ NGSolve within
  tolerance (the "confirmed by a second backend" done-when). Then **map the
  analytical-vs-FEM error** as a function of layer contrast and geometry, so the
  app/evaluator can flag when the analytical tier is trustworthy and when to
  escalate to FEM.
- **P4 S6 (optional) — Independent check + adapters.** Sim4Life field-only import
  (a solved file → `A`), a documented COMSOL adapter stub. Deferred to the
  cloud/lab; documented, not built.

## Testing strategy

- **Fast (no FEM, every push):** `mesh.py` geometry/topology from a fixture spec
  (electrode surfaces present, layers tagged) where it can run without a solve;
  the regime-map arithmetic on synthetic error curves.
- **`fem` (the FEM CI job):** MMS recovery to tolerance; analytical-vs-FEM
  agreement (homogeneous); the two-layer closed-form check; mesh convergence
  monotone-and-bounded; DOLFINx-vs-NGSolve agreement. These are the correctness
  gates that make an FEM number trustworthy.

## What to cut under pressure, in order

Drop P4 S6 (Sim4Life/COMSOL) — documented, not load-bearing. Then drop the NGSolve
second solver (keep MMS + analytical + two-layer closed-form as the known-answer
validation — rigorous on their own). Then drop layered anisotropy (keep isotropic
layers). Never cut the MMS/analytical validation or the convergence check — they
are what separate a trusted FEM number from a plausible-looking one.
