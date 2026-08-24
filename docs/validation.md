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

Concretely, that bar means: **the criterion column below is the claim, and the
measured column is only evidence for it.** A row passes when the sign of an effect,
the ordering of two conditions, or a ratio survives, not when a threshold matches a
published microamp value. Two things set the floor on how fine a difference is worth
reading. The threshold search bisects to within 4% of its bracketing rung (about a
quarter of a microamp at these amplitudes), and the modelling choices behind an
absolute number, meaning the mouse morphology, the nominal channel densities, and a
homogeneous rather than layered field, move it by far more than that. Differences of
a few percent between two of these numbers are not results.

Every reproduction in the tables below runs on the **analytical** field tier, so
none of these numbers is an FEM number. How the FEM tier earns its own trust is a
separate question, answered in [its own section below](#how-the-fem-tier-is-trusted).

## Run it yourself

The tables are generated, not typed. Regenerate the machine report the app reads:

```bash
uv run --extra cable python -m engine.validate.report   # writes app/validation_report.json
```

The reproductions are deterministic (fixed search parameters), so a correct engine
rewrites that file byte for byte. Assert them as tests instead:

```bash
uv sync --extra cable --extra dev --extra store --extra api
(cd engine/cable/mechanisms && uv run nrnivmodl .)      # once, to build the FM mechanisms
uv run python -m pytest tests/validate -q               # 18 tests, ~3.5 min: the whole scorecard
```

Both are exactly what CI runs. The rows that need no cable solve, meaning the field
physics and the Fan 2019 field-sharpening ratio, are in the fast suite on every push;
everything with a threshold in it is `neuron`-marked and runs in the `neuron` job, the
robustness sweeps included. Note what the tests assert: the **criterion** in the
right-hand column, not the measured number. A reproduction fails when a trend inverts,
not when a threshold moves by a microamp.

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

## How the FEM tier is trusted

The tables above are analytical-tier numbers, but the headline result and every
geometry study are FEM. The FEM tier has no literature reproductions of its own; it is
trusted by construction checks instead, all `fem`-marked and all run by CI:

```bash
conda activate retinode-fem
pytest tests/field -m fem      # 37 tests, ~4 min
```

| Check | What it rules out | Where |
|---|---|---|
| Method of manufactured solutions, on the real tissue mesh | a wrong discretization or assembly | `tests/field/test_fem_backend.py` |
| Agreement with the analytical half-space, on a domain large enough that truncation is small | a unit, sign, or magnitude error in the FEM chain | `tests/field/test_fem_backend.py` |
| Current conservation: a unit-current solve drives exactly 1 A out through the grounded boundary | a wrong flux boundary condition | `tests/field/test_fem_backend.py` |
| Two-layer closed form, plus a layered MMS across the sigma jump | mishandling of the conductivity interface | `tests/field/test_fem_layered.py` |
| Mesh convergence at fixed extent: `A` stops moving as the mesh sharpens | reporting a mesh-dependent number as a physical one | `tests/field/test_convergence_fem.py` |
| A second solver: DOLFINx and NGSolve on the *same* gmsh mesh agree to sub-percent | a bug in either library's assembly or unit chain | `tests/field/test_fem_agreement.py` |

`engine/field/regime.py` answers the adjacent question, how wrong the cheap tier is if
you pretend a layered retina is homogeneous, by sweeping the layer contrast and
recording the relative error against the FEM solve.

**What is still missing, and it is the honest gap.** Every check above is internal:
the code agreeing with closed forms, with itself under refinement, and with a second
open-source library on the same mesh. There is no third *independent implementation*
(Sim4Life or COMSOL, with a different mesher and vendor), and no comparison of an FEM
threshold against a measured ex vivo one. The first is designed and deliberately not
built, for the reason recorded in
[fem-independent-checks.md](fem-independent-checks.md); the second needs a lab.

One FEM number *is* pinned end to end: the headline
(`examples/reproduce_headline.py`, described in the
[README](../README.md#reproduce-the-headline-result)), which fails if the engine drifts
from the recorded thresholds. It is not part of CI, because it needs DOLFINx and NEURON
in one environment, so it is a check a reader runs rather than one a push enforces.

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
