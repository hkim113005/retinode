# Phase 4 — FEM accuracy layer: plan

**Goal.** A validated, drop-in open-source **FEM field backend** behind the
existing transfer-matrix contract, confirmed against known-answer solutions and a
second solver, and **extended to layered conductivity** — the retina's structure
the analytical backend rejects (`UnsupportedByBackend`) — with mesh-convergence
evidence per result and a map of where the analytical tier can be trusted.

**Done when** an open-source FEM field is validated and swappable behind the
contract, confirmed by a second backend, and the analytical-vs-FEM regime is
mapped. (The master plan called this lab-compute work; in fact DOLFINx runs
**locally** on Apple Silicon — see the toolchain note — so Phase 4 develops on the
Mac, and only Phase 5's sweeps need shared compute.)

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
| D4 | Toolchain | FEniCSx has **no pip wheel**, but conda-forge ships an **osx-arm64 build** (verified `fenics-dolfinx` 0.11.0) → the FEM env is **conda-forge**, *separate from uv*, and **runs locally on Apple Silicon** — no lab compute needed for development. The uv toolchain is untouched; a `fem`-marked, conda-only layer sits beside it. |
| D5 | Value-add scope | Layered conductivity is **in scope** (the whole point of FEM); homogeneous is validated first as the known-answer case. |
| D6 | Mesh | **gmsh** as the shared mesh front-end (neutral geometry → mesh both solvers read). |
| D7 | Boundary | Phase 4 is the **backend + validation**, not the sweep at scale (parametric FEM, surrogate, cluster/cloud = P5). Sim4Life/COMSOL are field-only/stub, documented/deferred. |

## Toolchain note (read first)

FEniCSx-first means the FEM layer lives in a **conda environment, separate from
uv** — but it **runs locally**: conda-forge ships `fenics-dolfinx` 0.11.0 for
osx-arm64 (Apple Silicon), verified. No lab compute is needed for Phase 4 — the
whole backend plus MMS/analytical validation develops on the Mac. Plan:

- `env/fem-environment.yml` — a conda-forge env (`fenics-dolfinx`, `gmsh`,
  `python`, `numpy`, `pytest`) for local FEM dev and CI. Create it with
  `conda create -n fenics -c conda-forge fenics-dolfinx gmsh python=3.12`, then
  `pip install -e . --no-deps` so `engine` imports. FEM work runs under this env;
  analytical / NEURON work stays under uv.
- The FEM CI job uses `mamba-org/setup-micromamba` to build the same env on the
  linux runner and runs `pytest -m fem`. The `test` / `test-neuron` jobs are
  unchanged.
- **P4 S1 opens with a (now low-risk) feasibility gate:** create the env and solve
  a trivial Poisson problem, locally and in CI. If DOLFINx somehow won't install
  cleanly, fall back to NGSolve-first (D1 flips) before building anything on it.

**Compute for scale (Phase 5, not here):** local suffices for Phase 4's
single-electrode solves and convergence checks. Big geometry sweeps escalate to
Stanford **FarmShare** (free Slurm) first, then **Sherlock** through a sponsoring
lab if true HPC parallelism is needed.

## Module layout

```
engine/field/
  backend.py       transfer-matrix contract + UnsupportedByBackend             [done]
  analytical.py    Tier-1 analytical backend                                    [done]
  mesh.py          neutral geometry -> gmsh mesh (electrode surfaces + layers)  [done]
  fem_fenicsx.py   DOLFINx backend behind the contract                          [done (homog + isotropic layered)]
  fem_ngsolve.py   NGSolve backend (second-solver cross-check)                  [P4 S5]
  convergence.py   mesh-refinement convergence check                           [done]
env/
  fem-environment.yml   conda-forge FEM env (dolfinx, gmsh)                     [done]
.github/workflows/ci.yml   + a `test-fem` job (micromamba)                      [done]
```

## Ordered steps

- **P4 S1 — Toolchain, feasibility gate, and mesh — done. Gate PASSED.** The
  local conda env (`env/fem-environment.yml`: `fenics-dolfinx` 0.11.0, `gmsh`
  4.15, Python 3.12) builds on Apple Silicon and a `test-fem` CI job builds the
  same spec via micromamba. **Feasibility gate passed:** a manufactured-solution
  Poisson solve (`u = 1 + x² + 2y²`, P2 elements) recovers the exact field to L2
  error `< 1e-9` — DOLFINx-first is confirmed, no NGSolve fallback needed
  (`tests/field/test_fem_gate.py`, deliberately gmsh-independent). `mesh.py` is a
  neutral parametric geometry — disk electrodes imprinted on the z=0 top face over
  a tissue slab, split into one tagged volume per conductivity layer, meshed by
  gmsh with graded refinement (fine at electrodes, coarse to the shell) and a
  `refined(factor)` knob for P4 S4. Boundary tags pinned: **each electrode surface
  its own physical group** (Neumann flux, applied per electrode by the backend),
  the rest of the top face **insulating** (natural zero-flux), sides + bottom
  **grounded** (Dirichlet V=0, the far-field truncation). Verified end-to-end:
  gmsh writes the mesh, DOLFINx reads it back with all tags intact, and the
  tagged measures are correct (electrode ≈ πr², shell + layer volumes exact).
  Pure geometry (partition/sizing/validation) is fast-tested without gmsh;
  gmsh+DOLFINx build is `fem`-marked (`tests/field/test_mesh.py`,
  `test_mesh_fem.py`).
- **P4 S2 — DOLFINx backend (homogeneous) + MMS/analytical — done.**
  `engine/field/fem_fenicsx.py`: `FenicsxBackend` behind the contract. Per
  electrode, a unit current is a Neumann flux `σ ∂V/∂n = 1/area` spread over the
  disk; the top face is insulating (natural zero-flux) and the outer shell is
  grounded. One LU solve per electrode → one column of `A`; the mesh is scaled
  microns→metres so assembly is pure SI, then `A = 1e-3 · V` recovers mV/µA. The
  half-space image the analytical tier adds by hand is **geometric** here (the
  slab *is* the half-space). Validated three ways (`test_fem_backend.py`, `fem`):
  **(a) MMS** — `u* = 1 + x² + 2y² + 3z²` recovered on the real tissue mesh to
  relative L2 `< 1e-8` (P2); **(b) analytical agreement** — on a homogeneous
  half-space with a ~3 mm grounded shell (truncation ≪ disk/mesh error), FEM `A`
  matches analytical `A` to **median 3.8%, max 4.5%** across z = 20–100 µm, same
  1/r decay, correct sign; **(c) current conservation** — a unit-current solve
  drives **−0.997 A** out through the ground (Kirchhoff to 0.3%), confirming the
  flux BC and unit chain. **Finding (recorded, not a bug):** the error grows with
  query distance only when the domain is too small — it is *truncation*
  (`err ≈ d/R`), so accuracy needs an adequately large grounded shell; the
  regime is mapped in P4 S5 and the convergence knob is P4 S4. The
  electrode-surface flux recovered by differentiating a P1 solution is unreliable
  (the ground integral is the trustworthy conservation check).
- **P4 S3 — Layered conductivity (the value-add) — done.** The backend now
  builds a **DG0 (cell-wise) σ** from the mesh's per-layer volume tags, so the σ
  jump sits exactly on the meshed interface and a conforming FEM enforces V- and
  flux-continuity across it. Isotropic layers are supported; diagonal anisotropy
  raises `NotImplementedError` (a planned extension — refused early, before any
  mesh build, so it is fast-tested). Validated two ways (`test_fem_layered.py`,
  `fem`): **(a) two-layer closed form** — for a unit source on the insulating
  surface of a two-layer half-space, FEM `A` matches the **image-series** in-layer
  potential to **median 3.4% / max 3.5%** (z = 20–40 µm inside the top layer);
  **(b) layered MMS** — a flux-continuous piecewise-linear exact solution
  (`σ₁A₁ = σ₂A₂`) is recovered to **relative L2 3.6e-16** (machine), through the
  backend's own `_build_sigma`. The **value-add is quantified and sign-checked**:
  a buried *resistive* layer (σ₂<σ₁) banks current up and raises the layer-1 field
  **1.3–1.7×** above the homogeneous-σ₁ field the analytical tier would give,
  while a *conductive* buried layer (σ₂>σ₁) drains it and lowers the field — a
  large, correctly-signed effect the analytical backend cannot represent (it
  rejects layered models by contract).
- **P4 S4 — Convergence + provenance — done.** `engine/field/convergence.py`:
  `mesh_convergence(base_domain, query_points, factors, tol)` solves on the domain
  refined by each factor (extent fixed, so truncation is constant and only the
  discretization changes) and records the curve — per level: mesh size, `‖A‖`, and
  the relative change `‖A_k − A_{k-1}‖ / ‖A_k‖` of the transfer matrix at the fixed
  query points. `converged` when the change between the two finest meshes < `tol`.
  Verified on a real solve: rel-change **0.034 → 0.018** across factors 1→3
  (`converged` at tol 0.05). The solver is **injectable**, so the convergence
  logic is fast-tested without dolfinx (a stub returns matrices with a known
  refinement trend); the real run is `fem`-marked. **Provenance:** `field_key`
  gained a `solve_params` argument (hashed when present); `FieldDomain.descriptor()`
  + `FenicsxBackend.solve_params()` expose the mesh extent/resolution + element
  degree, so a coarse-mesh `A` **can never be silently reused for a finer mesh**.
  The analytical backend passes no `solve_params`, so its keys — and every existing
  store/result key — are unchanged.
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
