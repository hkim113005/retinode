# Phase 3 plan: reproduce the published results (the credibility hinge)

**Goal.** Use the tool to recover the three published selectivity results, wire
them into CI regression tests, and surface them in a Validation screen. This is
the credibility hinge: a published result the tool reproduces in CI *and* shows
in the app is worth more than any prose.

**Done when** the reproductions pass in CI and are visible in the app.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Validation bar | **Trend / direction.** Assert the published *direction* holds (local return improves the SOW; bi-electrode raises the axon threshold; two subthreshold electrodes jointly fire); each record stores the measured ratio/values. Honest on the analytical tier + mouse morphology; matches the S5 philosophy. |
| D2 | Validation screen data | **Precomputed artifact.** A script runs the reproductions and writes a small JSON report (claim, measured, pass/fail); the app reads it and renders instantly. Regenerated when the model changes; CI's neuron job gates the underlying science. |
| D3 | Accuracy boundary | Absolute-value matching to primate ex-vivo data is **deferred to Phase 4+** (needs FEM + primate morphology). Phase 3 reproduces trends, not magnitudes. |
| D4 | Reproduction scenes | **Minimal hand-crafted scenes** that exhibit each effect (a small patch + specific electrode configs), not a pixel replica of each paper's geometry. |
| D5 | Compute | Reproductions are NEURON threshold searches, marked `neuron` (plus `slow` for the heavier ones) and run in the neuron CI job; scenes are kept small to bound the time. |

## Module layout

```
engine/validate/
  reproduction.py    Reproduction record (name/source/measured/criterion/passed)  [done]
  single_cell.py     S5 single-cell reproductions                                 [done]
  selectivity.py     Fan 2019: local-return selectivity gain                    [P3 S1]
  axon_avoidance.py  Vilkhu 2021: bi-electrode axon avoidance                    [P3 S2]
  nonlinearity.py    Vilkhu 2025: multi-electrode nonlinearity                   [P3 S3]
  report.py          run the population reproductions -> JSON report              [P3 S4]
app/
  ui.py / views.py   a Validation panel that reads the report + renders badges    [P3 S4]
```

## Ordered steps

- **P3 S1: Fan 2019, local-return selectivity gain. Done, with a finding.**
  `local_return_sharpens_the_field` compares a monopolar config against a
  local-return ring on one target/off-target pair. **Reproduced at the field
  level:** local return improves the soma-Ve selectivity `|Ve_target|/|Ve_off|`
  from 3.2× to 16.9×, robustly across geometries, which is Fan's mechanism.
  **Finding:** the full NEURON *somatic threshold-ratio* gain does **not**
  reproduce in this reduced tier (analytical field, mouse RGC). Activation is
  AIS/dendrite-dominated, so a tight return ring penalises the centred target
  while a loose one fails to suppress the off-target, and off-target thresholds
  even come out non-monotonic with distance. Recorded honestly with a `note`;
  magnitude and threshold validation are deferred to Phase 4 (FEM plus primate
  morphology). Fast test, no NEURON.
- **P3 S2: Vilkhu 2021, axon avoidance. Done, a clean reproduction.** The scene
  is a cell whose **axon of passage** crosses offset under the array. A confined
  (local-return ring) pattern collapses the activating function along that offset
  axon and **raises its threshold from 17 µA (monopolar) to 373 µA, a 22×
  avoidance**. Two checks: `confined_return_flattens_axon_af` (fast, analytical;
  peak AF ~1.5× lower) and `confined_return_avoids_axon_of_passage` (NEURON
  threshold). Both pass, with no AIS/dendrite confound, because an axon of passage
  is far from its own soma. That is why this reproduces where the somatic Fan case
  did not. It is the engine's home turf: explicit axons and the activating
  function.
- **P3 S3: Vilkhu 2025, multi-electrode summation. Done.** Two electrodes
  straddle the soma (±18 µm), each depolarising the AIS. Each **alone needs
  ~14 µA**, but **paired they fire at ~7 µA each, half as much**
  (`t_AB < min(t_A, t_B)`): two individually-subthreshold electrodes jointly cross
  threshold. A model treating the electrodes as independent (firing at the lower
  single threshold) would miss this; the multi-compartment model captures it.
  `subthreshold_electrodes_summate`, NEURON (~19 s). **Note on framing:**
  closely-spaced electrodes summate near-linearly at a shared site, as here, while
  widely-spaced ones activate *different* sites and combine *sub*-additively. The
  joint threshold therefore depends on arrangement, which a single-site proxy
  cannot capture. We reproduce the headline effect: a subthreshold pair fires the
  cell.
- **P3 S4: Validation screen (precomputed). Done.** `engine.validate.report`
  runs every reproduction (field physics, the S5 single-cell set, and the
  selectivity reproductions) into a JSON report, `app/validation_report.json`,
  regenerated with `uv run python -m engine.validate.report` and committed for the
  app to read. The app gained a **Validation** panel: a `13 / 13 reproduce` count
  and one row per reproduction (green or amber dot, name, measured value, source),
  so trustworthiness is *visible*, not merely asserted. `engine/` stays
  import-clean of `app/`. CI's neuron job independently gates the science; the
  panel is a snapshot of a gated result. See [validation.md](validation.md).

## Validation hardening (extra pass)

A thorough literature-and-physics validation sweep, added to raise confidence
before building further:

- **Field physics (fast):** reciprocity `G(a,b)=G(b,a)` (the one §11 property that
  was untested) and far-field decay (monopole ~1/r, dipole ~1/r²), which completes
  the analytical-backend property suite.
- **Single-cell literature (NEURON):** cathodic is more excitable than anodic
  (Ranck 1975); the strength-duration curve fits Weiss/Lapicque with a
  **sub-millisecond chronaxie** (~0.6 ms, rheobase ~6 µA), a quantitative upgrade
  to the S5 "decreases" check.
- **Robustness sweeps (NEURON, slow):** the axon-avoidance and summation
  reproductions are re-asserted across a *range* of geometries (offsets 30/50 µm;
  spacings 14/24 µm), so no reproduction can silently overfit one lucky scene.

## Testing strategy

- **Fast (no NEURON, every push):** the report's shape and the app panel builder
  (rendered from a fixture report dict: badges, claim, measured); `Reproduction`
  record fields; the reproduction *scene builders* where pure.
- **`neuron` / `slow` (neuron CI job):** each reproduction asserts its published
  trend (S1 local-return gain, S2 axon-threshold rise, S3 subthreshold-pair
  activation) on its minimal scene. These are the regression tests that break the
  build if a change silently degrades a reproduction.

## What to cut under pressure, in order

Drop the app Validation panel (P3 S4): the reproductions still gate CI, they are
just not visible in the app. Then drop S3, the hardest scene. Keep S1 and S2,
because a local-return selectivity gain and axon avoidance are the two most
load-bearing selectivity claims. Never weaken a reproduction's assertion to make
it pass. A reproduction that silently degrades is worse than one that honestly
fails.
