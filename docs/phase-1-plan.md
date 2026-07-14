# Phase 1 — Cable engine & evaluator: implementation plan

**Goal.** The NEURON population engine (multi-site activation, threshold search)
plus the fixed evaluator (selective operating window, thresholds, charge/safety,
activated area). **Done when** the analytical + NEURON pipeline produces a
defensible selectivity score for *any* spec, with single-cell thresholds matched
to Greenberg 1999 / Tsai 2012.

**Gates.** single cell spikes under an imposed field (Wk 3) → single-cell
thresholds match literature (Wk 4, Gate-1 checkpoint) → pipeline yields a
defensible SOW for any spec (Wk 5, **Gate 1**).

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Threshold definition | **Deterministic** (lowest amplitude firing ≥1 spike). Probabilistic 50%-activation layer deferred to Phase 3. |
| D2 | Channel model | **Adopt** the Fohlmeister–Miller `.mod` from [ModelDB #3673](https://modeldb.science/3673); compile with `nrnivmodl`. |
| D3 | Temperature | Pin `celsius` + per-channel **q10** (salamander ~22 °C → mammalian ~35 °C); recorded in provenance. |
| D4 | Morphology | Parametric multi-compartment: soma → **sodium-channel band** (high Na density, proximal axon) → intraretinal unmyelinated axon along the spec's `axon_um` → dendrite stub. |
| D5 | Off-target set | First-class, editable, hashed `OffTargetSet`; **provisional default** somata within ~120 µm + axons within ~30 µm of the array (a lab call). |
| D6 | Reciprocity/lead-field shortcut | Deferred to Phase 5 (sweeps). Full NEURON model is the Phase-1 deliverable. |

## Module layout

```
engine/cable/
  mechanisms/   vendored FM .mod (ModelDB #3673) + provenance
  activating.py Rattay activating function (pure)         [S1]
  morphology.py RGC spec -> NEURON Sections               [S2]
  channels.py   insert FM channels per compartment class  [S2]
  drive.py      apply Ve(t) via e_extracellular           [S3]
  spikes.py     multi-site detection + initiation site    [S6]
  threshold.py  bracketed non-monotonic amplitude search  [S4]
  population.py place cells; target + off-target runs      [S6]
engine/eval/
  safety.py     charge/phase, density, Shannon + material [S1]
  offtarget.py  OffTargetSet + selection                  [S1]
  metrics.py    SOW, activated area                        [S1]
  evaluator.py  the fixed scorer + evaluator_version       [S7]
  result.py     scored result + provenance                 [S7]
```

## Ordered steps (de-risked: pure arithmetic first, NEURON isolated)

- **S1 — Evaluator arithmetic (pure, no NEURON).** safety (charge, density,
  Shannon `log D = k − log Q`, `k ≤ 1.5`, + material limit), `OffTargetSet` +
  selection, SOW math, activating function. Fully on the fast CI job.
- **S2 — Single-cell model + intracellular sanity.** Vendor/compile FM `.mod`;
  parametric morphology with Na-band; `celsius`/q10. *Done:* injected current
  spikes correctly; silent below rheobase (Wk-3 gate).
- **S3 — Extracellular drive + sign.** Ve(t) = (A·I)·waveform(t) into
  `e_extracellular`. *Done:* cathodic-over-soma depolarizes and fires; anodic
  does not — the sign chain pinned end-to-end.
- **S4 — Threshold search.** Geometric ladder → bracket → bisect → verify above
  (detect upper-threshold/block). Returns the **lowest** activating amplitude +
  bracket + tolerance + monotonicity flag. (Not naive bisection.)
- **S5 — Single-cell threshold validation (Gate-1 checkpoint, Wk 4).**
  Greenberg-style threshold-vs-distance, soma-vs-axon, Na-band initiation;
  Tsai 2012 sanity. Stored as regression tests (target + tolerance + value).
  *Caveat: model-to-model agreement; real validation is Phase 3.*
- **S6 — Population, multi-site, trajectories, AF.** Multi-site detection with
  initiation-site attribution (dV/dt + amplitude, first-crosser); threshold
  averaged over a **distribution of axon trajectories** with reported spread.
- **S7 — Fixed evaluator → SOW (Gate 1, Wk 5).** Scores any spec; pins
  `evaluator_version`; refuses mismatched off-target sets. Uses the Phase-0 key:
  `result_key = combine(field_key, spec_hash(config), spec_hash(patch),
  evaluator_version, spec_hash(offtarget))`.

## Testing strategy

- **Fast (no NEURON, every push):** safety/Shannon arithmetic, SOW,
  activating function vs an analytic second derivative, off-target selection,
  and the threshold-search *logic* on synthetic activation curves (monotone +
  non-monotone).
- **`neuron`/`slow` (deliberate):** cell spikes, sign convention, extracellular
  drive, temperature effect, and physics property tests — threshold decreases
  with electrode proximity; threshold-vs-pulse-width follows a strength–duration
  relation; current-linearity.
- **Regression (gate checkpoints):** Greenberg/Tsai thresholds with stored
  target + tolerance + current value (also feed the Validation screen later).

## CI
The `.mod` files need `nrnivmodl`. Add a **separate CI job** (`cable`+`fem`
extras) that compiles mechanisms and runs the `neuron`-marked suite; the fast
job stays fast and unblocked.

## Risks & cut order (Phase-1 specific)
NEURON is the long pole. If S2–S5 overrun: keep the FM adoption (don't build
channels) → reduce morphology detail → collapse the trajectory distribution to
one nominal path → defer the AF diagnostic. S1 and the analytical field already
stand, so even a partial NEURON layer yields a usable score.

## Technical safeguards (from the design review)
- **Non-monotonic thresholds (T5):** bracketed scan, not bare bisection.
- **Temperature (T6):** pin `celsius`/q10 — FM is salamander.
- **Multi-site (T7):** real initiation criterion; distinguish initiation from
  propagation.
- **Sign chain (T8):** verify cathodic → `e_extracellular` → depolarization.
- **NEURON global state:** threshold runs are process-level; parallelism is a
  Phase-5 concern.

---

## S2 — single-cell model: research-current scope (approved)

Verified against the current literature (2023 review + 2025–26 work).

| Aspect | Decision | Basis |
|---|---|---|
| Channels | FM structure, **FM-2010 mammalian** (rat/cat) densities + Q10s | 2023 review; still the standard in 2025–26 |
| Vendoring | ModelDB #3673 `spike.mod`/`capump.mod` with attribution | reuse-with-citation |
| NEURON 9 | compiles as-is on 9.0.1 (no C++ adaptation needed) — **confirmed in S2a** | MOD→C++ migration risk retired |
| Morphology | **full dendritic arbor**, **mouse reconstructed SWC** (NeuroMorpho, Wang 2018) via Import3D | review: reduced models underestimate thresholds; cat/rat retinal reconstructions scarce on NeuroMorpho, mouse abundant |
| Species | mammalian single cell (mouse morphology + rat/cat FM-2010 channels); primate-specificity at the array/patch level | matches field + Lotlikar 2026 (macaque 512-array) |
| Temperature | **37 °C** + FM-2010 Q10s (applied at insertion, S2c) | review best practice |
| Activating function | **axon-of-passage diagnostic only**, never a whole-cell threshold surrogate | review: whole-cell AF R²=0.04 |
| Integrator | fixed `dt=0.025 ms`, CVODE off | deterministic; the FM mod is CVODE-incompatible |

**Build sub-steps:** S2a vendor+compile harness (done) · S2b SWC morphology — mouse RGC arbor + appended AIS/axon (done) · S2c FM-2010 channel insertion + 37 °C/Q10 · S2d spike sanity (Wk-3 gate).

Key sources: [2023 review](https://pmc.ncbi.nlm.nih.gov/articles/PMC10010067/); Fohlmeister–Miller [ModelDB #3673](https://modeldb.science/3673); [FM-2010 mammalian](https://pmc.ncbi.nlm.nih.gov/articles/PMC2887638/); [Lotlikar et al. 2026](https://arxiv.org/abs/2607.04063).
