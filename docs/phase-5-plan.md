# Phase 5 plan: study engine and compute scaling

**Goal.** Turn the single-array evaluator into a **geometry study engine**: sweep
over array geometry (electrode size, pitch, arrangement), **recomputing the field
per geometry** while **reusing the transfer matrix within each geometry**, down to
a **Pareto frontier** of selectivity against safety. It must be resumable,
cost-estimated, and backend-agnostic, with the P4 regime map deciding when a
geometry needs FEM and when the cheap analytical tier will do.

**Done when** a geometry sweep runs to a Pareto frontier, reusing transfer
matrices and recomputing fields per geometry, **without manual bookkeeping**
(interrupt-and-resume, no recomputation of cached work). Matches the master plan's
Phase-5 done-when.

**Why it is mostly composition (and therefore low-risk).** The hard pieces already
exist and are validated:

- **`engine/study/sweep.py`:** config sweeps on a *fixed* array. Backend-agnostic
  (any `FieldBackend`), store-backed and content-addressed (it skips cached
  results), reusing one field solve across configs, with an injectable
  `thresholds_provider` for fast tests. Phase 5 wraps this in an *outer geometry
  loop*.
- **`engine/store`:** the content-addressed `Project` (FieldCache, ResultStore,
  provenance), with `field_key`/`result_key` now **FEM-mesh-aware** (P4 S4). This
  *is* the resumability substrate; no new job database is needed.
- **`engine/study/cost.py`:** `estimate_sweep_cost` and `benchmark_cell`. Phase 5
  extends both to the geometry axis.
- **`engine/field`:** the analytical, DOLFINx, and NGSolve backends, plus the
  **regime map** (`regime.py`) that says when analytical can be trusted (P4 S5).
- **`pareto_selectivity_safety`:** the frontier reducer, already in `sweep.py`.

So Phase 5 is a geometry generator, an outer loop that composes the above, a
resumable runner, local parallelism, and an optional surrogate. Not a rewrite.

## Locked decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The new axis | **Geometry.** The outer loop moves over array geometry (diameter, pitch, arrangement); the inner loop is the existing config sweep, reusing that geometry's one transfer matrix. `pareto_selectivity_safety` reduces the union to a frontier. |
| D2 | Backend selection | **Regime-aware.** The sweep runs on any `FieldBackend`; for each geometry and conductivity it consults the **P4 S5 regime map**, using the cheap analytical tier where that is trustworthy and escalating to FEM only where layer contrast demands it. Most of a sweep stays cheap. |
| D3 | Resumability | **Rides the content-addressed store, not a bespoke job DB.** Each geometry's `A` (FieldCache) and results (ResultStore) are keyed by the P4 S4 provenance keys, so a re-run skips anything already stored. The master plan's "job model" is realized as store checkpointing plus a progress callback. |
| D4 | Execution | **Local parallelism first.** A process-pool adapter parallelizes independent per-geometry evaluations across cores, following Phase 4's "runs locally" stance. Slurm (FarmShare → Sherlock) and the Sim4Life cloud are **documented adapter interfaces, deferred**, as in P4 S6. |
| D5 | Cost | **An estimate gates every launch.** `n_geometry × (per_field_solve + n_config × per_threshold)`, with `per_field_solve` benchmarked on the actual mesh (FEM) or taken as ~0 (analytical). Surfaced before running, so there is no accidental multi-day job. |
| D6 | Surrogate | **Optional and last.** A coarse-to-fine grid is the default. A Gaussian-process (or simpler) emulator over the score surface, proposing where to sample next, is the optional final step and the first cut. |
| D7 | Deliverable | **The Pareto frontier**, each point tagged with the **backend tier** that produced it and, where available, the **trajectory-distribution spread**, so a design finding arrives with its tier and sensitivity attached. |

## Module layout

```
engine/study/
  sweep.py           config sweep on a fixed array (backend-agnostic, store-backed)  [done]
  cost.py            cost estimate + cell benchmark                                   [done]
  geometry.py        parametric array generators (diameter/pitch/arrangement -> spec) [done]
  geometry_sweep.py  outer geometry loop: field per geometry, config sweep reused     [done]
  runner.py          resumable, store-checkpointed runner + progress callbacks       [done]
  parallel.py        local process-pool execution adapter                            [done]
  surrogate.py       optional GP emulator over the selectivity-score surface         [done]
docs/
  compute-adapters.md   Slurm (FarmShare/Sherlock) + Sim4Life-cloud adapter design   [done, deferred]
```

## Ordered steps

- **P5 S1: Parametric geometry generators. Done.** `engine/study/geometry.py`:
  `ArrayGeometry` (frozen and hashable: diameter, pitch, arrangement, aperture)
  plus `build_array`, a pure function filling a disk aperture on z=0 with a square
  (`"grid"`) or hexagonal (`"hex"`) lattice at nearest-neighbour spacing `pitch`.
  Verified: grid gives centre plus 4 axial, hex gives centre plus 6, pitch is
  uniform, ids are deterministic (sorted y-then-x) and unique, and geometries are
  hashable and value-equal. `pitch >= diameter` is enforced so generated arrays
  **never overlap** and pass `engine.spec.validate` (checked in the tests).
  `geometry_grid` enumerates the diameter × pitch product, dropping overlapping
  combinations, which is the parameter list P5 S2 sweeps. Fast-tested (pure spec,
  no field or NEURON).
- **P5 S2: Geometry sweep and Pareto frontier. Done.**
  `engine/study/geometry_sweep.py`: `geometry_sweep(geometries, patch,
  conductivity, config_factory, ...)` builds each array, solves its field **once**,
  runs the config sub-sweep on it by delegating to `sweep()` (so the field is
  reused across configs and served from the store if cached), and reduces the
  union of all results with `pareto_selectivity_safety`. Two composition points
  make heterogeneous geometries work: a **config factory** (`config_factory(array)
  -> configs`, needed because electrode ids differ per geometry;
  `monopolar_center` is provided) and **regime-aware backend choice**
  (`resolve_field_tier`: analytical for homogeneous or mild-contrast layers
  approximated as homogeneous, FEM for strong contrast, per D2).
  `GeometrySweepResult` maps every frontier point back to its
  geometry (`geometry_of`, `pareto_geometries`). Backend-agnostic and store-backed,
  so the orchestration is fast-tested with an injected `thresholds_provider` (loop
  coverage, non-dominated frontier, geometry trace-back, tier selection, full-cache
  re-run, progress callback); one **`neuron`-marked end-to-end** test runs a real
  analytical-tier sweep over two geometries (~50 s), confirming that real fields
  and threshold searches drive the frontier and that a resumed run recomputes
  nothing. **This is the done-when's core.**

  > **Corrected in P8 S4.** `resolve_field_tier` reads the *conductivity* only.
  > The analytical backend is a point source, so it cannot see electrode diameter
  > or pitch, and a geometry sweep on that tier returns a byte-identical field for
  > every geometry. Geometry sweeps are now forced onto FEM. See
  > [phase-8-findings.md](phase-8-findings.md).

- **P5 S3: Resumability and provenance at scale. Done.**
  `engine/study/runner.py`. The store already persists each result the moment it
  is evaluated (P5 S2), so the substrate is there. S3 adds the two things that make
  it a study you can run unattended. **`study_status`** asks a store *how far along
  a study is* without computing anything: it recomputes each geometry's
  `result_key` and checks membership, returning `n_complete`, `fraction_done`, and
  `remaining_geometries`. That is the provenance-at-scale query.
  **`run_geometry_study`** is the same run as `geometry_sweep` but emits a
  structured `GeometryProgress` per geometry (index and total, `from_cache`,
  cumulative cached versus evaluated, `fraction`) for a progress bar or a long
  log. **Interrupt-and-resume is verified:** a run that crashes after the first
  geometry (a progress callback that raises) leaves that
  geometry durably stored; re-invoking against the same store completes the study
  with **only the completed geometry served from cache** (`n_cached == 1`) and
  `study_status` going 0→1→3 complete across the crash and resume. This is the
  "without manual bookkeeping" clause. Fast-tested (no NEURON/FEM).
- **P5 S4: Local parallel execution. Done.** `engine/study/parallel.py`:
  `parallel_geometry_sweep` runs independent per-geometry evaluations across worker
  processes and returns the same result as the serial sweep. Two constraints shaped
  it. **NEURON's per-process global state** forces process-level rather than thread
  parallelism (a `ProcessPoolExecutor`), and the **store is not
  concurrent-write-safe** (HDF5, parquet), so workers compute with `store=None` and
  *return* results while the **main process records them serially**. That makes
  "content-addressed writes keep workers collision-free" hold trivially.
  Resumability rides the same store: a geometry already fully cached is served and
  **never dispatched** (proved with a poisoned executor). `SerialExecutor` is the
  injectable in-process fallback (`max_workers=1`) that also lets the orchestration
  be fast-tested without pickling or NEURON. Verified: parallel results equal the
  serial results and frontier; progress and full re-run caching hold; and a **real
  ProcessPool plus NEURON** run over two geometries in two worker processes took
  **~30 s against ~50 s serial**, an actual speedup, then resumed fully cached.
  Cost gating before launch is the existing `estimate_sweep_cost` (D5).
- **P5 S5: Cluster and cloud adapters (documented, deferred). Done.**
  [compute-adapters.md](compute-adapters.md) holds the Slurm (FarmShare →
  Sherlock via a sponsoring lab) and Sim4Life-cloud execution-adapter designs,
  **documented, not built**, since both need lab or cloud access. This mirrors
  P4 S6. The key point recorded there: `parallel.py` already isolates *where* work
  runs (the `executor`) from *what* it is (a picklable `_GeometryJob`), and workers
  compute with `store=None` while the main process records. A new target, whether a
  `SlurmExecutor` array-job dispatcher or a Sim4Life field backend, is therefore a
  drop-in `Executor` or backend and changes nothing in the sweep, store, or Pareto
  path. The gate: wire Slurm when a sweep's cost estimate (D5) exceeds the local
  wall-clock budget.
- **P5 S6 (optional): Surrogate model. Done.** `engine/study/surrogate.py`: a
  Gaussian-process emulator over geometry `(diameter, pitch) -> score`, in
  numpy and scipy only (RBF kernel, Cholesky, standardised inputs; `fit_gp` and
  `predict` return a posterior mean and std). `active_search` seeds an even spread
  of the candidate set, then repeatedly fits the GP and evaluates the highest
  **UCB** (`mean + kappa·std`) unsampled candidate, converging on the high-score
  region **without a full grid**. It is deterministic (spread seeds plus argmax),
  so runs are reproducible. `search_geometries` is the geometry adapter: the score
  is `score_of(geometry)`, injected, which is a real geometry sweep's selectivity
  in use and a synthetic surface in tests. Verified: the GP interpolates its
  training points and is uncertain between them, and on a smooth score surface the
  search lands within 10% of the true optimum while evaluating **~25% of the
  grid**, beating seed-only sampling. Fast-tested (synthetic score, no NEURON or
  FEM). Optional and first to cut, as scoped.

## Testing strategy

- **Fast (no NEURON/FEM, every push):** geometry generators (correct arrays, no
  overlaps, deterministic + hashable); geometry-sweep orchestration with injected
  field + threshold providers (per-geometry loop, config reuse, Pareto union);
  runner checkpoint/skip logic against a fake store; geometry-sweep cost
  arithmetic; surrogate proposal math on synthetic score surfaces.
- **`neuron` / `slow`:** a small real geometry sweep (a few geometries × a few
  configs) to a Pareto frontier on the analytical tier, asserting the frontier is
  non-dominated and that a resumed run does no NEURON work.
- **`fem`:** a 1–2-geometry sweep on the DOLFINx backend, confirming the geometry
  loop drives a fresh FEM field per geometry and caches by the mesh-aware key.

## What to cut under pressure, in order

Drop the **surrogate (S6)**: a coarse grid still finds the frontier, just with
more solves. Then drop the **cluster/cloud docs (S5)**, already deferred. Then
drop **local parallelism (S4)**, since serial sweeps are slower but correct.
**Never cut** the geometry sweep and Pareto reduction (S2) or the store-backed
resumability (S3): together they *are* the Phase-5 done-when.

## Compute note

Local-first: parallelize per-geometry work across cores, keep grids coarse, and
lean on the **analytical tier wherever the regime map permits**, since a
per-geometry analytical `A` is closed-form and instant. Escalate large **FEM**
geometry sweeps to Stanford **FarmShare** (free Slurm) then **Sherlock** (through
a sponsoring lab); route Sim4Life work through the deferred cloud adapter. The
real bottleneck is the **NEURON threshold search** (~15–25 s per cell), so a full
geometry × config × population sweep is compute-bound. That is exactly why
store-backed resumability (S3), cost gating (S5/D5), and regime-aware tier
selection (D2) are load-bearing rather than polish.

> **Read with P8 S4.** Regime-aware tier selection turned out not to make geometry
> sweeps cheap: the analytical tier cannot see electrode geometry at all, so a
> geometry sweep is FEM-only and costs ~28 s per geometry. Cost gating matters
> more as a result, not less.
