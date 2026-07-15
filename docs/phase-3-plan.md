# Phase 3 — Reproduce the published results (credibility hinge): plan

**Goal.** Use the tool to recover the three published selectivity results, wire
them into CI regression tests, and surface them in a Validation screen. This is
the credibility hinge — a published result the tool reproduces in CI *and* shows
in the app is worth more than any prose.

**Done when** the reproductions pass in CI and are visible in the app.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Validation bar | **Trend / direction.** Assert the published *direction* holds (local return improves the SOW; bi-electrode raises the axon threshold; two subthreshold electrodes jointly fire); each record stores the measured ratio/values. Honest on the analytical tier + mouse morphology; matches the S5 philosophy. |
| D2 | Validation screen data | **Precomputed artifact.** A script runs the reproductions and writes a small JSON report (claim, measured, pass/fail); the app reads it and renders instantly. Regenerated when the model changes; CI's neuron job gates the underlying science. |
| D3 | Accuracy boundary | Absolute-value matching to primate ex-vivo data is **deferred to Phase 4+** (needs FEM + primate morphology). Phase 3 reproduces trends, not magnitudes. |
| D4 | Reproduction scenes | **Minimal hand-crafted scenes** that exhibit each effect (a small patch + specific electrode configs), not a pixel replica of each paper's geometry. |
| D5 | Compute | Reproductions are NEURON threshold searches — `neuron` (+`slow` for the heavier ones), run in the neuron CI job; scenes kept small to bound time. |

## Module layout

```
engine/validate/
  reproduction.py    Reproduction record (name/source/measured/criterion/passed)  [done]
  single_cell.py     S5 single-cell reproductions                                 [done]
  selectivity.py     Fan 2019 — local-return selectivity gain                    [P3 S1]
  axon_avoidance.py  Vilkhu 2021 — bi-electrode axon avoidance                   [P3 S2]
  nonlinearity.py    Vilkhu 2025 — multi-electrode nonlinearity                  [P3 S3]
  report.py          run the population reproductions -> JSON report              [P3 S4]
app/
  ui.py / views.py   a Validation panel that reads the report + renders badges    [P3 S4]
```

## Ordered steps

- **P3 S1 — Fan 2019: local-return selectivity gain.** Build a target +
  off-target patch. Score a **monopolar** config (single electrode over the
  target, distant return) and a **local-return** config (bipolar / return on the
  array). **Reproduce:** the local-return SOW ratio exceeds the monopolar one —
  local return concentrates current and improves selectivity. Store both ratios.
- **P3 S2 — Vilkhu 2021: bi-electrode axon avoidance.** Place a cell whose **axon
  of passage** runs under the array. A monopolar electrode over the axon fires it
  at a low threshold; a **bi-electrode** pattern that flattens the activating
  function (∂²Ve/∂s²) along the axon **raises the axon threshold** (avoidance)
  while still reaching the target soma. Uses `activating_function_along_axon` +
  multi-site thresholds. Store the axon-threshold ratio and the AF flattening.
- **P3 S3 — Vilkhu 2025: multi-electrode nonlinearity.** Two electrodes, each at
  an amplitude that is **subthreshold alone**, jointly cross threshold — the
  any-compartment summation no linear single-site proxy captures. **Reproduce:**
  at an amplitude where each electrode alone does not fire the cell, both together
  do (and the combined threshold falls below the linear-superposition
  prediction). Store the single vs joint thresholds.
- **P3 S4 — Validation screen (precomputed).** `report.py` runs S1–S3 (and the
  S5 single-cell set), producing a JSON report of `Reproduction` records;
  regenerated via a documented command and committed for the app to read. The app
  gains a **Validation** panel listing each reproduction — claim, measured value,
  and a pass/fail badge — so the tool's trustworthiness is visible, not just
  asserted. `engine/` stays import-clean of `app/`.

## Testing strategy

- **Fast (no NEURON, every push):** the report's shape and the app panel builder
  (rendered from a fixture report dict — badges, claim, measured); `Reproduction`
  record fields; the reproduction *scene builders* where pure.
- **`neuron` / `slow` (neuron CI job):** each reproduction asserts its published
  trend (S1 local-return gain, S2 axon-threshold rise, S3 sub+sub activation) on
  its minimal scene — the regression tests that break the build if a change
  silently degrades a reproduction.

## What to cut under pressure, in order

Drop the app Validation panel (P3 S4) — the reproductions still gate CI, just not
visible in the app. Then drop S3 (the hardest scene). Keep S1 + S2: a
local-return selectivity gain and axon avoidance are the two most load-bearing
selectivity claims. Never weaken a reproduction's assertion to make it pass — a
reproduction that silently degrades is worse than one that honestly fails.
