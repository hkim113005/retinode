# Phase 2 — Persistence store, configuration sweeps, and the minimal app: plan

**Goal.** Turn the single-shot evaluator (Phase 1) into a *cached, sweepable*
engine, then put a thin usable app on top. Evaluate many configurations on a
fixed array cheaply by reusing the transfer matrix; persist fields and results
content-addressed; log provenance so any result traces to exactly what produced
it; rank a shortlist. Then a Python dashboard over that engine.

**Done when** (infra) a configuration sweep on a fixed array runs to a ranked
shortlist, reusing transfer matrices and cached results across overlapping runs
without manual bookkeeping, every result traceable; **and** (app, P2b) someone
who is not us can design an array, set a configuration, and read a selectivity
result without touching code.

**Scope boundary.** Phase 2 is **configuration** sweeps on a **fixed** array —
one transfer matrix reused over many current patterns (the cheap, Tier-1 half of
§9). **Physical-geometry** sweeps (field recomputed per array), the surrogate
model, cluster/cloud execution, resumable async jobs, and cost-at-scale are
**Phase 5**. Phase 2 stays synchronous, analytical-tier + NEURON.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Track | **Infra first, then app.** Build the store + sweep engine, then a dashboard (P2b) that consumes it — so the UI has real sweep/cache capability to show, not single evaluations. |
| D2 | Store format | **parquet + HDF5** (the §10 layout): parquet for scalar result metrics, HDF5 for `A` matrices, JSON sidecars for nested/curve fields. Adds `pandas`/`pyarrow`/`h5py` (none installed yet). |
| D3 | Transfer-matrix reuse | **Do it now.** A per-placed-cell `SolvedField` (the transfer matrix over the cell's segments) is computed once and reused across every config and amplitude in a fixed-array sweep. This is the whole point of the geometry/config split. |
| D4 | Concurrency | **Synchronous.** Async/resumable jobs, cluster, and cloud adapters are Phase 5. |
| D5 | Sweep axes | **Configuration only:** steering weights, waveform shape, return mode — never amplitude (threshold search already sweeps it), never geometry (Phase 5). |
| D6 | `field_key` correction | Extend `field_key` to include the **query points / cell placement**: the Phase-1 seed keyed only (backend, array, conductivity), but a per-cell `A` cache is only correct when placement is in the key. |

## Module layout

```
engine/cable/
  solved.py     SolvedField: A cached over a placed cell's segments;   [P2 S1]
                compute_ve/threshold search reuse it, not rebuild
engine/store/
  keys.py       field_key + result_key (Phase 1; field_key extended)   [P2 S1]
  fields.py     HDF5 transfer-matrix cache, keyed by field_key         [P2 S2]
  results.py    parquet result store + JSON sidecars, by result_key    [P2 S2]
  project.py    Project: on-disk workspace (open/create, put/get)      [P2 S2]
  provenance.py append-only run log (one record per run)               [P2 S3]
engine/study/
  sweep.py      configuration sweep over a fixed array + ranking       [P2 S4]
  cost.py       pre-sweep cost estimate from a one-eval benchmark      [P2 S5]
app/            Python dashboard (Dash/Plotly) over the engine         [P2b]
```

## Ordered steps

- **P2 S1 — Solved-field reuse (the efficiency core) — done.** `SolvedField`
  holds a placed cell's transfer matrix `A` (over its segments) and turns each
  config into a cheap `A @ current_vector`; `solve_field` builds it once per
  (cell, array, conductivity, backend). `multisite_threshold` solves once and
  reuses `A` across every amplitude, and accepts a pre-solved field so a caller
  (the P2 S4 sweep) reuses it across configurations too. `compute_ve` delegates
  to `solve_field`; `field_key` gained an optional query-points term (D6) with a
  cross-machine-stable `query_points_digest`. Field solves collapse from
  O(amplitudes × configs) to O(1) per cell (a 19-amplitude search now solves `A`
  once, Ve bit-identical, threshold unchanged). Wall-clock is unchanged on the
  analytical tier (a solve is ~0.02 ms; NEURON dominates) — the win lands at the
  FEM tier and in sweeps.
- **P2 S2 — The project store (on-disk, content-addressed).** The §10 layout:
  `specs/` (hash-named canonical JSON), `cache/fields/` (`A` by `field_key`,
  HDF5), `results/` (parquet scalars + JSON sidecars by `result_key`),
  `project.json` manifest. A `Project` object: open/create, put/get result and
  field, list/index, and cache-hit reuse (a present `result_key` skips the
  solve). **Done when** results and fields round-trip and a re-put is a cache hit.
- **P2 S3 — Provenance.** Append-only `provenance.log`, one record per run: spec
  hashes *and* values, software versions (NEURON, numpy, retinode), git commit,
  seeds, timestamps. **Done when** every stored result has a matching provenance
  record and the key it was computed under replays deterministically.
- **P2 S4 — Configuration-sweep engine.** `sweep(array, patch, conductivity,
  configs, *, store, off_target_set, backend)` evaluates each config (reusing
  P2 S1, caching via P2 S2, logging via P2 S3, skipping cached `result_key`s) and
  returns the collected `EvaluationResult`s plus a ranked shortlist over the
  usable operating window (margin/ratio) and a Pareto helper (selectivity vs.
  safety margin). Config generators: an explicit list plus steering-weight and
  waveform-shape helpers. **Done when** a sweep produces a ranked shortlist
  reusing `A` and skipping already-cached results.
- **P2 S5 — Cost estimate (minimal).** `estimate_sweep_cost(n_configs, n_cells,
  per_eval_s)` from a one-eval benchmark, surfaced before a sweep runs. The
  at-scale estimator (per-mesh FEM benchmark, realized-vs-estimated logging) is
  Phase 5.
- **P2b — The minimal usable app.** A Python dashboard (Dash/Plotly, per §17)
  over the engine: Patch, Array, Tissue, Stimulus, and Results screens on the
  analytical tier, with the live-preview loop and the field, activation, and
  scorecard views, driving a sweep and reading its shortlist. `engine/` stays
  import-clean of `app/` (§4). **Done when** a non-author can design an array,
  set a configuration, and read a selectivity result without code.

## Testing strategy

- **Fast (no NEURON, every push):** store round-trips (result/field put→get,
  cache hit, missing-key, corrupted-file handling); `field_key`/`result_key`
  determinism and placement-sensitivity (D6); sweep orchestration and ranking
  via an injected thresholds provider; Pareto correctness on synthetic results;
  cost-estimate arithmetic; provenance record shape and append semantics.
- **`neuron`/`slow`:** the A-reuse end-to-end mini-sweep (2–3 configs on a fixed
  small patch) asserting each cell's `A` is built once and reruns hit the cache;
  one full `evaluate`→store→reload cycle.
- **App (P2b):** a headless smoke render of each screen plus a scripted
  design→configure→result path; the data-contract payloads (§16) asserted stable.

## What to cut under pressure, in order

Drop the dashboard (P2b) — the infra is the load-bearing deliverable and is
usable from Python. Then drop parquet/HDF5 for npz+JSON (fewer deps). Then drop
the Pareto helper (keep flat ranking). Then drop the cost estimate. Never cut
P2 S1 (reuse) or the provenance record — they are why the results are cheap and
trustworthy.
