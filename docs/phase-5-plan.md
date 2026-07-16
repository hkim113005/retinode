# Phase 5 — Study engine and compute scaling: plan

**Goal.** Turn the single-array evaluator into a **geometry study engine**: sweep
over array geometry (electrode size, pitch, arrangement), **recomputing the field
per geometry** while **reusing the transfer matrix within each geometry**, to a
**Pareto frontier** of selectivity vs safety — resumably, cost-estimated, and
backend-agnostic (the P4 regime map decides when a geometry needs FEM vs the cheap
analytical tier).

**Done when** a geometry sweep runs to a Pareto frontier, reusing transfer
matrices and recomputing fields per geometry, **without manual bookkeeping**
(interrupt-and-resume, no recomputation of cached work). Matches the master plan's
Phase-5 done-when.

**Why it is mostly composition (and therefore low-risk).** The hard pieces already
exist and are validated:

- **`engine/study/sweep.py`** — config sweeps on a *fixed* array: backend-agnostic
  (any `FieldBackend`), store-backed and content-addressed (skips cached results),
  reuses one field solve across configs, injectable `thresholds_provider` for
  fast tests. Phase 5 wraps this in an *outer geometry loop*.
- **`engine/store`** — the content-addressed `Project` (FieldCache + ResultStore +
  provenance), with `field_key`/`result_key` now **FEM-mesh-aware** (P4 S4). This
  *is* the resumability substrate; no new job database is needed.
- **`engine/study/cost.py`** — `estimate_sweep_cost` + `benchmark_cell`. Phase 5
  extends it to the geometry axis.
- **`engine/field`** — analytical + DOLFINx + NGSolve backends, and the **regime
  map** (`regime.py`) that says when analytical can be trusted (P4 S5).
- **`pareto_selectivity_safety`** — the frontier reducer, already in `sweep.py`.

So Phase 5 is: a geometry generator, an outer loop that composes the above, a
resumable runner, local parallelism, and an optional surrogate — not a rewrite.

## Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The new axis | **Geometry.** The outer loop moves over array geometry (diameter, pitch, arrangement); the inner loop is the existing config sweep, reusing that geometry's one transfer matrix. `pareto_selectivity_safety` reduces the union to a frontier. |
| D2 | Backend selection | **Regime-aware.** The sweep runs on any `FieldBackend`; per geometry+conductivity it consults the **P4 S5 regime map** to use the cheap analytical tier where trustworthy and escalate to FEM only where layer contrast demands it. Most of a sweep stays cheap. |
| D3 | Resumability | **Rides the content-addressed store, not a bespoke job DB.** Each geometry's `A` (FieldCache) and results (ResultStore) are keyed by the P4 S4 provenance keys; a re-run skips anything already stored. The master plan's "job model" is realized as store checkpointing + a progress callback. |
| D4 | Execution | **Local parallelism first.** A process-pool adapter parallelizes independent per-geometry evaluations across cores (Phase 4's "runs locally" stance). Slurm (FarmShare → Sherlock) and Sim4Life cloud are **documented adapter interfaces, deferred** (like P4 S6). |
| D5 | Cost | **Estimate gates every launch.** `n_geometry × (per_field_solve + n_config × per_threshold)`, `per_field_solve` benchmarked on the actual mesh (FEM) or ~0 (analytical). Surfaced before running — no accidental multi-day job. |
| D6 | Surrogate | **Optional and last.** A coarse-to-fine grid is the default; a Gaussian-process (or simpler) emulator over the score surface — proposing where to sample next — is the optional final step and the first cut. |
| D7 | Deliverable | **The Pareto frontier**, each point tagged with the **backend tier** that produced it and (where available) the **trajectory-distribution spread**, so a design finding is defensible with tier + sensitivity attached. |

## Module layout

```
engine/study/
  sweep.py           config sweep on a fixed array (backend-agnostic, store-backed)  [done]
  cost.py            cost estimate + cell benchmark                                   [done]
  geometry.py        parametric array generators (diameter/pitch/arrangement -> spec) [P5 S1]
  geometry_sweep.py  outer geometry loop: field per geometry, config sweep reused     [P5 S2]
  runner.py          resumable, store-checkpointed runner + progress callbacks        [P5 S3]
  parallel.py        local process-pool execution adapter                            [P5 S4]
  surrogate.py       optional GP emulator over the selectivity-score surface          [P5 S6]
docs/
  compute-adapters.md   Slurm (FarmShare/Sherlock) + Sim4Life-cloud adapter design    [P5 S5, deferred]
```

## Ordered steps

- **P5 S1 — Parametric geometry generators.** `geometry.py`: pure, deterministic,
  hashable functions mapping geometry parameters — electrode **diameter**,
  **pitch**, **arrangement** (grid / hex), count/extent — to canonical
  `ElectrodeArray` specs, validated (no electrode overlaps, within a stated
  aperture). This is the axis a geometry sweep moves along. Fast-tested (pure
  spec; no field, no NEURON).
- **P5 S2 — Geometry sweep + Pareto frontier.** `geometry_sweep.py`: for each
  generated geometry, solve the field **once** (via the injected `FieldBackend`),
  run the config sub-sweep **reusing that `A`** (delegating to `sweep()`), collect
  every result, and reduce the union with `pareto_selectivity_safety`.
  Backend-agnostic; injectable field + threshold providers so the *orchestration*
  is fast-tested without NEURON/FEM. **This is the done-when's core: geometry
  sweep → Pareto frontier.** The regime-aware tier choice (D2) is wired in here.
- **P5 S3 — Resumability + provenance at scale.** Thread a `Project` store through
  the geometry sweep so each geometry's `A` and results are cached by the P4 S4
  provenance keys; a re-run **skips completed geometries with no recompute**.
  Per-geometry progress callbacks. Verified by interrupting a sweep and resuming
  it to completion from the store. This is the "without manual bookkeeping" clause.
- **P5 S4 — Local parallel execution.** `parallel.py`: a process-pool adapter that
  runs independent per-geometry evaluations concurrently, gated by the S5 cost
  estimate. Content-addressed store writes keep parallel workers collision-free.
  Serial stays the default and fallback.
- **P5 S5 — Cluster/cloud adapters (documented, deferred).**
  `docs/compute-adapters.md`: the Slurm (FarmShare → Sherlock via a sponsoring lab)
  and Sim4Life-cloud execution-adapter interfaces — job submission shape, how the
  store syncs results back — **documented, not built** (needs lab/cloud access),
  mirroring P4 S6. Ties to the Sim4Life import adapter in
  [fem-independent-checks.md](fem-independent-checks.md).
- **P5 S6 (optional) — Surrogate model.** `surrogate.py`: a Gaussian-process (or
  simpler) emulator over the selectivity score as a function of geometry
  parameters, proposing the next geometry to sample (active learning /
  coarse-to-fine), so a sweep converges on the Pareto-relevant region without a
  full grid. Optional; first to cut.

## Testing strategy

- **Fast (no NEURON/FEM, every push):** geometry generators (correct arrays, no
  overlaps, deterministic + hashable); geometry-sweep orchestration with injected
  field + threshold providers (per-geometry loop, config reuse, Pareto union);
  runner checkpoint/skip logic against a fake store; geometry-sweep cost
  arithmetic; surrogate proposal math on synthetic score surfaces.
- **`neuron` / `slow`:** a small real geometry sweep (a few geometries × a few
  configs) to a Pareto frontier on the analytical tier — assert the frontier is
  non-dominated and that a resumed run does no NEURON work.
- **`fem`:** a 1–2-geometry sweep on the DOLFINx backend, confirming the geometry
  loop drives a fresh FEM field per geometry and caches by the mesh-aware key.

## What to cut under pressure, in order

Drop the **surrogate (S6)** — a coarse grid finds the frontier, just with more
solves. Then drop **cluster/cloud docs (S5)** — already deferred. Then drop
**local parallelism (S4)** — serial sweeps are slower but correct. **Never cut**
the geometry sweep + Pareto (S2) or the store-backed resumability (S3): together
they *are* the Phase-5 done-when.

## Compute note

Local-first: parallelize per-geometry work across cores, keep grids coarse, and
lean on the **analytical tier wherever the regime map permits** (per-geometry
analytical `A` is closed-form and instant). Escalate large **FEM** geometry sweeps
to Stanford **FarmShare** (free Slurm) then **Sherlock** (sponsoring lab); route
Sim4Life work through the deferred cloud adapter. The real bottleneck is **NEURON
threshold search** (~15–25 s per cell), so a full geometry × config × population
sweep is compute-bound — which is exactly why store-backed resumability (S3), cost
gating (S5/D5), and regime-aware tier selection (D2) are load-bearing, not polish.
