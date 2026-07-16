# P5 S5 — Cluster and cloud execution adapters: deferred, by design

**Status: documented, not built.** Like P4 S6, this step is scoped from the start
as a design note rather than code (phase-5-plan.md, D4 and the cut list). Local
parallelism (P5 S4) already runs geometry sweeps across every core of the
development machine; cluster and cloud execution matter only once a sweep outgrows
one machine, which needs access this work does not yet have. This records the
adapter designs so they are a small, well-understood addition when that access
exists.

## Why deferred

- **Slurm on FarmShare / Sherlock** needs a Stanford **FarmShare** account (free,
  shared) or, for real HPC parallelism, **Sherlock** through a sponsoring lab. The
  scheduler, partitions, and quotas are site-specific and not worth encoding until
  a sweep actually needs them.
- **Sim4Life cloud** needs a **commercial license** and ties to the deferred
  Sim4Life field-import adapter ([fem-independent-checks.md](fem-independent-checks.md)).

None of these blocks the Phase-5 done-when: a geometry sweep already runs to a
Pareto frontier, resumably and in parallel, on local hardware (P5 S1–S4).

## The seam they plug into (the reason deferral is cheap)

`engine/study/parallel.py` already isolates *where work runs* from *what the work
is*. `parallel_geometry_sweep` takes an `executor` — any
`concurrent.futures.Executor` — and:

- ships each geometry as a **picklable `_GeometryJob`** (geometry + patch +
  conductivity + backend + config factory), and
- has each worker compute with **`store=None`**, returning a `GeometryOutcome`;
  the **main process records results serially**, so no remote worker ever writes
  the store.

So a new execution target is a new `Executor` (or a thin dispatcher with the same
submit/collect shape). The compute moves; the sweep, the store, the resumability,
and the Pareto reduction do not change.

## Slurm adapter (FarmShare → Sherlock)

A `SlurmExecutor` implementing the `Executor` interface, or a batch dispatcher:

1. **Serialize jobs** — pickle each `_GeometryJob` to a shared-filesystem path
   (FarmShare/Sherlock home or scratch).
2. **Submit** — one `sbatch` **array job**, one array index per geometry, each
   task running a small entry script that unpickles its job, calls `_run_job`, and
   pickles the returned `GeometryOutcome` back to disk. NEURON/DOLFINx are already
   the per-geometry compute; the cluster env provides them (a conda env module or
   a container).
3. **Collect** — the main process waits on the array job (`sacct`/polling),
   unpickles each outcome, and — exactly as the local path does — **records results
   to the store in the main process**. Resumability is unchanged: geometries
   already in the store are never submitted.

Escalation order: **FarmShare first** (free, fine for tens–hundreds of geometries),
**Sherlock** when a sweep needs true HPC parallelism and a lab can sponsor
allocation.

## Sim4Life cloud adapter

Sim4Life solves **fields** in the cloud, not the whole pipeline. So the cloud role
is the **field-solve step**, wrapped as a `FieldBackend` (the import adapter in
[fem-independent-checks.md](fem-independent-checks.md)): export each geometry's
neutral geometry spec, solve in Sim4Life, import the solved field → `A`, then run
the (local) NEURON evaluation. It is a field-tier option the regime map can select
into, not a separate execution engine — and it is deferred with the import adapter.

## The gate for un-deferring

Wire the Slurm adapter when a sweep's **cost estimate** (`estimate_sweep_cost`,
D5) exceeds the local wall-clock budget — i.e. when `n_geometry × per-geometry
time` on `cpu_count-1` cores is no longer acceptable. Build the `SlurmExecutor`
against FarmShare first (lowest friction), validate that a small array job
round-trips outcomes and records identically to the local path, then scale to
Sherlock. Sim4Life follows its import adapter. None of this changes the sweep
API — only the `executor` passed in.
