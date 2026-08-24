# Validation: literature and physics reproductions

Correctness is the product, so the tool's trustworthiness is both **enforced in
CI** (every reproduction is a regression test) and **visible in the app** (the
Validation panel, from a precomputed report). This page is the human-readable
scorecard.

**Bar: trend and direction, not absolute magnitude.** On the analytical tier with
a mouse-RGC morphology, the tool reproduces the *directions and ratios* of
published results reliably. Matching exact primate ex-vivo magnitudes needs both a
faithful layered field and a primate morphology. Phase 4 delivered the first (the
FEM tier, with layered conductivity); the primate morphology does not exist here,
so absolute magnitudes stay out of reach.

Every reproduction in the tables below runs on the **analytical** field tier, so
none of these numbers is an FEM number.

Regenerate the machine report with:

```bash
uv run --extra cable python -m engine.validate.report
```

It writes `app/validation_report.json`, which the Validation screen reads.

## Field physics (exact, fast)

| Check | Measured | Criterion |
|---|---|---|
| Reciprocity `G(a,b)=G(b,a)` | equal to 1e-9 | reciprocal |
| Far-field decay | monopole 1/r^0.99, dipole 1/r^1.97 | monopole ~1, dipole ~2 |

Plus the existing analytical-backend suite: units vs closed form, half-space
doubling, 1/r decay, spherical symmetry, monotonic falloff, insulating-boundary
mirror symmetry, near-field regularization, superposition.

## Single-cell vs literature (NEURON)

| Claim | Source | Measured | Criterion |
|---|---|---|---|
| Threshold rises with distance | Greenberg 1999 | 12 / 26 / 54 µA at 25/40/60 µm | monotonic ↑ |
| Axon of passage more excitable than soma | Vilkhu 2021 | axon 15 vs soma 26 µA | axon < soma |
| Spike initiates at the AIS | Jeng/Fried | initiation = AIS | not the soma |
| Strength-duration falls with pulse width | Greenberg 1999 | 82/46/26/16 µA at 50/100/200/400 µs | monotonic ↓ |
| Threshold in physiological range | Tsai 2012 | 26 µA | 1–150 µA |
| Cathodic more excitable than anodic | Ranck 1975 | cathodic 26 vs anodic 38 µA | cathodic lower |
| Strength-duration chronaxie sub-ms | Weiss/Lapicque | rheobase 6.4 µA, chronaxie 0.59 ms | 0.05–1.0 ms |

## Selectivity vs literature (NEURON + analytical)

| Claim | Source | Measured | Criterion |
|---|---|---|---|
| Local return sharpens the field | Fan 2019 | soma-Ve selectivity 3.2× → 16.9× | local > monopolar |
| Confined pattern flattens the axon AF | Vilkhu 2021 | peak axon AF 1.78e-3 → 1.20e-3 | confined lower |
| Confined pattern avoids the axon of passage | Vilkhu 2021 | axon threshold 17 → 373 µA (22×) | confined ≥ monopolar |
| Two subthreshold electrodes jointly fire | Vilkhu 2025 | each 14 µA alone, paired 7 µA | pair < single |

Robustness sweeps re-assert the axon-avoidance and summation reproductions across
a range of geometry (offsets 30/50 µm; spacings 14/24 µm), so none rests on one
lucky scene.

## Two honest scope notes

1. **Fan 2019 reproduces the field-sharpening *mechanism*, not the full somatic
   threshold gain.** In the reduced model, AIS and dendrite activation confounds
   the somatic threshold ratio: a tight return ring penalises the centred target,
   while a loose one fails to suppress the off-target. The mechanism is robust.
   The threshold magnitude needs a faithful layered field, and it has not been
   re-measured on the FEM tier that Phase 4 delivered.
2. **The one negative is what makes the set credible.** No reproduction was tuned
   until it passed. Where the reduced tier cannot support a claim, that is
   recorded honestly and deferred.
