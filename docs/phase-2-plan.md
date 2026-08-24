# Phase 2 plan: persistence store, configuration sweeps, and the minimal app

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

**Scope boundary.** Phase 2 is **configuration** sweeps on a **fixed** array:
one transfer matrix reused over many current patterns (the cheap, Tier-1 half of
§9). **Physical-geometry** sweeps (field recomputed per array), the surrogate
model, cluster/cloud execution, resumable async jobs, and cost-at-scale are
**Phase 5**. Phase 2 stays synchronous, on the analytical tier plus NEURON.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Track | **Infra first, then app.** Build the store and sweep engine, then a dashboard (P2b) that consumes it, so the UI has real sweep and cache capability to show, not single evaluations. |
| D2 | Store format | **parquet + HDF5** (the §10 layout): parquet for scalar result metrics, HDF5 for `A` matrices, JSON sidecars for nested/curve fields. Adds `pandas`/`pyarrow`/`h5py` (none installed yet). |
| D3 | Transfer-matrix reuse | **Do it now.** A per-placed-cell `SolvedField` (the transfer matrix over the cell's segments) is computed once and reused across every config and amplitude in a fixed-array sweep. This is the whole point of the geometry/config split. |
| D4 | Concurrency | **Synchronous.** Async/resumable jobs, cluster, and cloud adapters are Phase 5. |
| D5 | Sweep axes | **Configuration only:** steering weights, waveform shape, return mode. Never amplitude (the threshold search already sweeps it) and never geometry (Phase 5). |
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

- **P2 S1: Solved-field reuse (the efficiency core). Done.** `SolvedField`
  holds a placed cell's transfer matrix `A` (over its segments) and turns each
  config into a cheap `A @ current_vector`; `solve_field` builds it once per
  (cell, array, conductivity, backend). `multisite_threshold` solves once and
  reuses `A` across every amplitude, and accepts a pre-solved field so a caller
  (the P2 S4 sweep) reuses it across configurations too. `compute_ve` delegates
  to `solve_field`; `field_key` gained an optional query-points term (D6) with a
  cross-machine-stable `query_points_digest`. Field solves collapse from
  O(amplitudes × configs) to O(1) per cell (a 19-amplitude search now solves `A`
  once, Ve bit-identical, threshold unchanged). Wall-clock is unchanged on the
  analytical tier, where a solve costs ~0.02 ms and NEURON dominates; the win
  lands at the FEM tier and in sweeps.
- **P2 S2: The project store (on-disk, content-addressed). Done.** `Project`
  is the §10 workspace: `specs/` (hash-named canonical JSON), `cache/fields/`
  (`A` by `field_key`, HDF5), `results/` (per-result JSON sidecar + `index.parquet`
  by `result_key`), `project.json` manifest. put/get/has for results, fields, and
  specs; a present `result_key` is the cache hit the sweep (P2 S4) uses to skip a
  re-solve. The JSON sidecar is the round-trip source of truth (via a dedicated
  inf-tolerant, dict/tuple-faithful `serialize` for the result tree); the parquet
  index carries the flat scalar metrics for ranking. `engine.store` stays
  import-light so `engine.eval → store.keys` never pulls the `h5py`/`pyarrow`
  extra. **Note:** `result_key` identifies inputs, not thresholds, so two runs of
  one scene share a key and upsert to a single index row (the store deduping
  correctly).
- **P2 S3: Provenance. Done.** Append-only `provenance.log`, one JSON line per
  run: the content hashes, the off-target set inline (not a registry spec type),
  software versions (python/numpy/retinode, neuron if present), the retinode git
  commit, seeds (empty until a stochastic layer), and a UTC timestamp. `RunRecord`
  is self-checking: it carries the components of `field_key`/`result_key` and
  replays both. `Project.record_run` is the one call per evaluation. It stores the
  result, the spec *values* behind its hashes (`array`/`config`/`patch`/
  `conductivity` → `specs/`), and the record, so every stored result has a
  matching provenance entry. The log is append-only (a re-run appends, never
  mutates); `provenance.py` stays import-light.
- **P2 S4: Configuration-sweep engine. Done.** `sweep(array, patch,
  conductivity, configs, *, store, ...)` evaluates each config over a fixed array,
  wiring the phase together: the population is placed and solved **once** (P2 S1)
  and reused across every config; a store hit on `result_key` is served from disk
  (P2 S2); a fresh eval records result + provenance (P2 S3). Solves are lazy (first
  miss), so an all-cached re-run does no NEURON work. `rank_by_window` (usable
  first, then margin, then selectivity) and `pareto_selectivity_safety`
  (non-dominated: SOW ratio vs. safety headroom) build the shortlist;
  `waveform_shape_sweep`/`steering_sweep` are the pure config generators.
  **Verified (NEURON):** a 2-config sweep solves target+off-target's fields once
  each (spy calls == 2), and a re-run serves both from the store with zero solves.
- **P2 S5: Cost estimate (minimal). Done.** `estimate_sweep_cost(n_configs,
  n_cells, per_threshold_s, *, per_solve_s, n_cached)` models the sweep the way it
  spends time (fields solved once per cell, then a threshold search per cell per
  un-cached config), and it is pure and fast-tested. `benchmark_cell` times one
  solve and one threshold search on the target cell for the per-unit times;
  `estimate_from_benchmark` extrapolates; `format_duration` renders it (`~1h 44m
  30s to sweep 380 of 500 configs…`). A safety feature for the user's time; the
  at-scale estimator is Phase 5.
- **P2b: The minimal usable app. Done.** A single-page Dash/Plotly dashboard
  (`app/`) over the engine: a control rail (Array / Stimulus / Patch / Tissue), a
  **live analytical field preview** (Ve heatmap with electrodes + cells, updates
  instantly, no NEURON), and an **Evaluate** action that runs the real pipeline
  into a scorecard: the safe-and-selective operating window with target
  threshold, selectivity, and safety, badged usable or blocked. Pure `scene` (UI →
  spec) and `views` (data contract + figure) are fast-tested; `engine/` stays
  import-clean of `app/` (§4, verified). **Done:** design array → set config →
  read a selectivity result, no code. Run with `uv run python -m app` (needs the
  `app` + `cable` extras).

  > **Retired in P7 S8.** The Dash UI (`app/ui.py`, `app/__main__.py`,
  > `app/assets/`) and the `app` extra are gone; the React client at `app/web`
  > reached parity and replaced it. `app/scene.py` and `app/views.py`'s data
  > functions remain, because the API imports `scene` and `views` is the
  > independent oracle its parity tests assert against. This section is kept as
  > the record of what Phase 2 built.

## Testing strategy

- **Fast (no NEURON, every push):** store round-trips (result/field put→get,
  cache hit, missing-key, corrupted-file handling); `field_key`/`result_key`
  determinism and placement-sensitivity (D6); sweep orchestration and ranking
  via an injected thresholds provider; Pareto correctness on synthetic results;
  cost-estimate arithmetic; provenance record shape and append semantics.
- **`neuron`/`slow`:** the A-reuse end-to-end mini-sweep (2–3 configs on a fixed
  small patch), asserting each cell's `A` is built once and that re-runs hit the
  cache; one full `evaluate`→store→reload cycle.
- **App (P2b):** a headless smoke render of each screen plus a scripted
  design→configure→result path; the data-contract payloads (§16) asserted stable.

## What to cut under pressure, in order

Drop the dashboard (P2b), because the infra is the load-bearing deliverable and
is usable from Python. Then drop parquet/HDF5 for npz + JSON (fewer deps). Then
drop the Pareto helper (keep flat ranking). Then drop the cost estimate. Never
cut P2 S1 (reuse) or the provenance record: they are why the results are cheap
and trustworthy.
