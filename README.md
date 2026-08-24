# Retinode

An epiretinal electrode-geometry selectivity testbed.

Retinode answers one question: **which electrode geometry and current
configuration fires the cells you want without firing the ones you don't?**
Describe a hypothetical epiretinal array and a stimulus. Retinode places a
population of retinal ganglion cells (RGCs) together with their axons of passage,
drives them with the array's extracellular field, finds each cell's activation
threshold, and scores the **safe-and-selective operating window**: how far the
amplitude can rise before a bystander cell fires or a charge-safety limit is
crossed. From there it compares designs, sweeps geometry to a
selectivity-versus-cost frontier, and exports a ranked shortlist of
configurations worth testing in tissue.

> **New here? Start with [`docs/SETUP.md`](docs/SETUP.md).** It is the one document to
> follow from a fresh clone: three tiers, so you run the 449-test suite in about five
> minutes before deciding whether to install NEURON or the FEM environment. Every
> command in it was run on the machine it documents.
> [`docs/user-guide.md`](docs/user-guide.md) is the walkthrough of the app once it is
> up. The next section of this README states the physics; after that it is the
> architecture and development reference.

## What is actually being solved

Three models in series, each with a fixed contract between them, plus the charge
constraint that bounds the result. The file named in each paragraph is where that
paragraph is enforced, so a claim here can be checked against code rather than taken
on trust.

**1. The extracellular field.** Quasi-static volume conduction in the tissue,
`div(sigma grad V) = 0`, solved once per electrode at unit current. Two tiers solve it:

- **Analytical** (`engine/field/analytical.py`): point sources in a *homogeneous*
  half-space. The array sits on an insulating substrate at z = 0, imposed by the method
  of images, so a source on that plane gives `V = I / (2*pi*sigma*r)`. Source distances
  are floored at the electrode radius so the near field stays bounded. Homogeneous
  isotropic conductivity only; anything layered is refused rather than approximated.
- **FEM** (`engine/field/fem_fenicsx.py`, DOLFINx): the same equation on a meshed
  tissue slab. Each electrode face carries a uniform Neumann flux
  `sigma dV/dn = I / area`, the rest of the z = 0 plane is insulating (the natural
  zero-flux condition), and the outer shell (sides and bottom) is grounded, `V = 0`.
  Homogeneous or isotropic-layered conductivity, and the only tier that sees an
  electrode's size, shape, or 3D body.

Both hand back the same object, the **transfer matrix** `A`, where `A[i, j]` is the
potential at query point *i* per unit current on electrode *j*, in **mV/µA**. The
problem is linear, so any stimulus is `Ve[mV] = A @ I[µA]`: one solve per electrode,
after which every configuration over that geometry is a weighted sum.

**2. The cell.** A multi-compartment NEURON RGC, built once per cell in the patch.
Morphology is a vendored **mouse** RGC reconstruction (soma plus complete dendrites);
retinal reconstructions rarely trace the axon, so the hillock, the sodium-channel band
(AIS), and the intraretinal axon are appended (`engine/cable/morphology.py`). Membrane
dynamics are the Fohlmeister-Miller channel set (Na, delayed-rectifier K, A-type K, Ca,
and Ca-activated K) at 37 °C with q10 = 2.5 scaling of the gating kinetics; gNa is
raised in the AIS, which is where the spike initiates (`engine/cable/channels.py`).
Sections are subdivided by the d-lambda rule. The field enters through NEURON's
`extracellular` mechanism (`e_extracellular = Ve`), stepped through the pulse at fixed
time step, because the FM mechanism is not CVODE-compatible. Cells are solved one at a
time and independently: there is no synaptic or ephaptic coupling between them.

**3. Threshold, and what "selectivity" is operationalised as.** Spikes are detected at
**every** compartment, not just the soma, so a cell counts as activated if anything on
it fires, and the earliest-firing segment is the initiation site
(`engine/cable/multisite.py`). That is what makes an axon of passage a first-class
off-target. Extracellular activation is non-monotonic (a cell can fall silent again at
high amplitude), so the search is not a bare bisection: it climbs a geometric ladder to
bracket the lowest activating amplitude, bisects inside that bracket, then scans above
to record any upper block (`engine/cable/threshold.py`). The default search range is
1 to 500 µA, and a cell that has not fired by the cap is recorded as *not measured*,
never as *has no threshold*.

Write `T` for the target's threshold and `O` for the lowest off-target threshold:

```
selective margin  =  O - T                    ratio = O / T
safety ceiling S  =  the largest amplitude inside the charge limits
operating window  =  [T, min(O, S))           usable margin = min(O, S) - T
```

That usable margin **is** the selectivity score, and `limiting` records which of the
two capped it. If a bystander was searched but never fired below the cap, `O` is
reported as the cap and flagged as a lower bound rather than as unbounded selectivity
(`engine/eval/metrics.py`).

**4. Charge safety.** Per phase, `Q = |I| * PW` and charge density `D = Q / A`. A
configuration is unsafe if it crosses either the **Shannon criterion**
(`log10 D + log10 Q > k`, with `k = 1.5`) or an optional material charge-injection
limit on `D` (`engine/eval/safety.py`). Unsafe configurations are excluded from any
shortlist.

**Units and frame**, pinned in `engine/spec/conventions.py` and asserted in tests:
length µm, current µA (**cathodic, the excitatory phase, is negative**), conductivity
S/m, time µs, potential mV. `z = 0` is the array plane, `+z` runs into the tissue, and
cells sit at `z > 0`.

## Terminology

- **Geometry**: the *physical* array, meaning electrode sizes, shapes, positions,
  pitch, and placement. Changing geometry requires re-solving the field.
- **Configuration** (or *stimulus*): the *current delivery*, meaning which electrodes
  source and which return, with what weights and waveform, over a fixed geometry.
  Changing configuration is cheap, a weighted sum over an already-solved field.
- **Transfer matrix**: the field each electrode produces per unit current, and the
  universal handoff between the field solvers and the cells.
- **Accuracy tier**: which field solver produced a number, **analytical** or **FEM**,
  attached to every result. There is no third tier: the DOLFINx-versus-NGSolve
  cross-check is a test the FEM tier must pass, not a badge a result can carry.
- **Off-target** (or *bystander*): any cell or axon of passage that should stay silent.
  A spike anywhere on it closes the operating window. Which cells count is an explicit,
  hashed object, not a constant: by default a cell within 120 µm of the target soma, or
  one whose axon passes within 30 µm of an electrode (`engine/eval/offtarget.py`).
- **Operating window**: the amplitude band `[T, min(O, S))` that fires the target and
  nothing else while staying inside the charge limits. Its width is the selectivity
  score.

## What Retinode does not claim

The tool **screens and generates hypotheses**. It proposes configurations for ex vivo
or in vivo testing, and simulation alone cannot make it a ground-truth oracle. The
limits travel with the numbers instead of hiding in a footnote:

- **Trend, not magnitude.** The reproductions match the *direction and ratio* of
  published results, not absolute primate ex vivo thresholds.
  [docs/validation.md](docs/validation.md) is the scorecard, and it records the one
  reproduction that holds only in part.
- **Mouse RGC morphology.** It was the one available RGC reconstruction with complete
  dendrites and a proper soma, and truncated dendrites bias extracellular thresholds.
  Primate specificity is captured at the array and patch scale, not at the single cell
  (`engine/cable/morphologies/PROVENANCE.md`).
- **Every number carries its accuracy tier** (analytical or FEM) and its sensitivity.
  Treat the comparison between two designs as the signal, not either absolute number.
- **The analytical tier is a point source**, blind to an electrode's size and shape.
  Any question in which the geometry itself is the variable is FEM-only
  ([docs/phase-8-findings.md](docs/phase-8-findings.md)).
- **No novel design finding yet.** The headline below is a *capability* result: the
  engine resolves a geometry effect the cheap tier cannot see. Which geometries
  dominate the frontier, and why, is still open.
- **A population of two, in the default scene.** The shipped Compare and headline scene
  is one target cell and one bystander at a set distance (`app/scene.py`), not a
  realistic mosaic. The evaluator takes an arbitrary patch, but nothing in this repo
  yet builds a dense one, so the absolute window widths are scene artefacts even where
  the comparison between designs is not.

## Install and run

Full instructions, with real timings and the failure modes, are in
[`docs/SETUP.md`](docs/SETUP.md). The shape of it:

- **Tier 1**, about 5 minutes: [uv](https://docs.astral.sh/uv/) and Python 3.12, then
  `uv sync --extra dev --extra store --extra api` and the fast test suite. The engine
  core is numpy/scipy only, so everything heavy is an opt-in extra.
- **Tier 2**, about 15 minutes: the `cable` extra (NEURON) plus the compiled
  Fohlmeister-Miller mechanisms, then the FastAPI service and the React client. This is
  where you score a real operating window in the browser. On macOS the `neuron` wheel
  has a packaging defect that can break `nrnivmodl`; SETUP.md carries the fix.
- **Tier 3**, 30 minutes or more: the conda `retinode-fem` env, the only place DOLFINx,
  gmsh, and NEURON live together, because DOLFINx ships no pip wheel. Needed for FEM,
  for anything 3D, and for the headline reproduction below. The app dispatches FEM jobs
  to that interpreter as a subprocess (`$RETINODE_FEM_PYTHON`), so you never switch
  environments by hand, and it says plainly when a request requires FEM.

Run `python3 scripts/doctor.py` at any point: it is standard library only and read
only, and it reports which of the three tiers this machine actually has.

The app itself is a FastAPI service over the engine with a React client. Design an
array, stimulus, and patch, watch the live field preview, and evaluate the selective
operating window without touching code.

Screens:

- **Compare**: live field, isopotential contours, scorecard, FEM tier, and run history.
  It also authors a **3D electrode body**, either a pillar, dome, or taper, or an
  uploaded STEP/BREP solid, scored on FEM with the real bodied field and rendered in
  the 3D loupe. See [docs/custom-electrode.md](docs/custom-electrode.md).
- **Study**: a diameter × pitch sweep resolved to a selectivity-versus-cost frontier.
  Geometry sweeps are forced onto the FEM tier (roughly 28 s per geometry) because the
  analytical tier cannot see geometry at all.
- **Candidates**: a charge-safe ranked shortlist, exportable as a report and as a
  machine-readable list.
- **Validation**: what the engine reproduces, read from a precomputed report.

Every plot exports as figure-quality SVG or high-DPI PNG. `⌘K` (or `Ctrl-K`) opens the
command palette.

> The Phase-2 Dash dashboard was retired in Phase 7 once the React client reached
> parity. `app/views.py` outlived it as the API's independent test oracle.

## Reproduce the headline result

One command reproduces the tool's reason for existing: **electrode geometry changes
selectivity, and only the FEM tier can see it.** Two flat disks (10 µm and 30 µm) score
*byte-identically* on the analytical tier, a point source blind to an electrode's
extent, and *distinctly* on FEM. The script checks the FEM numbers against the values
recorded in [`docs/phase-8-findings.md`](docs/phase-8-findings.md) and **exits non-zero
if the engine has drifted**, so it is a reproducibility guarantee rather than a demo.

It needs the conda `retinode-fem` env (FEM + NEURON), which is
[Tier 3 of the setup](docs/SETUP.md#tier-3-the-fem-environment-and-the-headline-result-30-minutes-or-more),
and takes ~1–2 minutes (56 s measured on an Apple Silicon Mac). The
scene is the shipped default: a single flat disk at the origin, a 200 µs cathodic
monophasic pulse, homogeneous sigma = 1 S/m, the target soma 20 µm above the array
plane and one bystander 40 µm lateral of it (`app/scene.py`). **The tabulated numbers
are the target cell's activation threshold in µA**, the `T` of the operating window.

```bash
FEMPY=/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python
$FEMPY examples/reproduce_headline.py
```

```
  diameter |   analytical |        FEM
-----------+--------------+-----------
      10 µm |      8.31 µA |    9.49 µA
      30 µm |      8.31 µA |   10.20 µA

✓ analytical: d10 and d30 are identical (8.31 µA): the point source is blind to diameter, as claimed
✓ FEM: d10 (9.49 µA) and d30 (10.20 µA) differ: the geometry effect the analytical tier can't see
✓ provenance: d10 FEM 9.49 µA matches the recorded 9.49 µA
✓ provenance: d30 FEM 10.20 µA matches the recorded 10.20 µA

HEADLINE REPRODUCED ✓. Geometry changes selectivity; FEM resolves it, the analytical point source does not.
```

**What "reproducible" guarantees here:** the FEM thresholds must land within ±0.30 µA
of the recorded values or the command fails, and the analytical pair must be identical,
since the point source is diameter-blind by construction. Results are identified by
provenance (`result_key` / `offtarget_hash`), and the engine refuses to compare across
differing off-target sets.

**Threshold is where the script stops, but not where the effect stops.** Scoring the
same two scenes end to end, the FEM usable window is 4.75 µA for d10 against 5.46 µA
for d30 (selectivity ratio 1.50 against 1.53), while on the analytical tier both
diameters return the same 8.31 µA threshold and the same 4.51 µA window. So the
geometry moves the selectivity score, not only the threshold. The **charge-safety
ceiling** also moves with diameter, but on *both* tiers, because it is charge density
over area rather than a field effect, and here it is not what caps the window. Only the
four thresholds in the table are pinned by the script; treat these window figures as
context, not as a second regression check.

**What it does not guarantee.** Three caveats, none of which the script hides:

- The ±0.30 µA band is a **drift tripwire on a deterministic search**, not an
  uncertainty estimate. The threshold search is a fixed ladder plus bisection with no
  randomness, so a correct engine reproduces these values exactly; the band exists to
  absorb solver and platform noise, not to express an error bar.
- The **effect is modest in absolute terms.** The bisection resolves a threshold to
  within 4% of its bracketing rung, about 0.24 µA on this scene, so the 0.71 µA gap
  between d10 and d30 is roughly three search steps. What is unambiguous is the
  *qualitative* claim, because the analytical pair is identical to every printed digit
  while the FEM pair is not.
- **CI does not run this script.** It needs DOLFINx and NEURON in one environment, and
  the CI FEM job runs `pytest tests/field -m fem` only. Drift is caught when a human
  runs the command, which is why it is one command.

The physical fidelity ceiling is unchanged: mouse RGC morphology,
trend-not-magnitude validation ([docs/validation.md](docs/validation.md)).

## Architecture

Four layers, with a strict rule: **the engine knows nothing about the application, and
the spec objects are the single source of truth.**

```
engine/   # pure library; no fastapi, no UI imports
  spec/       # domain model, validation, serialization, hashing
  field/      # transfer-matrix contract + backends
  cable/      # NEURON population + threshold search
  eval/       # the fixed evaluator
  study/      # sweep + surrogate + cost model
  store/      # cache, project store, provenance
  validate/   # property tests, cross-backend, reproductions
api/      # FastAPI; imports engine, never the reverse
app/      # scene translation + view payloads; web/ is the React client
tests/
docs/
```

One boundary is load-bearing: **`engine/` may not import from `api/` or `app/`.** That
rule is what makes the later polished-app build a re-skin rather than a rewrite.

### Provenance, and what the cache is keyed by

Nothing here is cached by filename. A **field solve** is stored under `field_key`, the
combination of backend name, array hash, conductivity hash, the mesh and element
settings for FEM, and the query points, so a coarse-mesh transfer matrix can never be
served for a finer one (`engine/store/keys.py`). A **scored result** is stored under
`result_key`, which is `field_key` plus the stimulus, the patch, the evaluator version,
the off-target definition, and the safety and overlap parameters. Change any one of
those and you get a fresh key rather than a stale hit; the evaluator version exists
precisely so a scoring change cannot silently mix with old numbers.

Every run also appends one JSON line to a provenance log carrying those hashes, the
off-target set inline, the software versions and git commit, and a timestamp
(`engine/store/provenance.py`). The record is self-checking: it can replay `field_key`
and `result_key` from its own components and confirm it describes the computation that
actually ran. This is why the engine refuses to compare two results whose
`offtarget_hash` differs: the selective window means nothing across different
definitions of who counts as a bystander.

## Status

**Phases 1–8 complete**, from the single-configuration evaluator through to the
polished application, and Phase 9 (packaging, docs, and the one-command reproduction)
has landed. Retinode places biophysical (Fohlmeister-Miller) RGCs, drives them with the
array's extracellular field, finds each cell's threshold with multi-site detection (a
spike at any compartment counts, which makes an axon of passage a first-class
off-target), and scores a **safe-and-selective operating window** with the provenance
key that identifies it. On top of that evaluator sit a **FEM field tier** (DOLFINx) for
shaped and 3D electrodes and for geometry comparison, a **geometry-sweep study engine**
with a selectivity-versus-cost Pareto frontier, and the **FastAPI + React application**
described above.

The phase plans record the build step by step, with decisions and findings:

- [`docs/phase-1-plan.md`](docs/phase-1-plan.md) … [`docs/phase-9-plan.md`](docs/phase-9-plan.md):
  the per-phase build logs.
  [phase-7-design.md](docs/phase-7-design.md) is the UX bar for the app, and
  [phase-8-findings.md](docs/phase-8-findings.md) records the analytical-tier limits
  and their fix.
- [`docs/retinode-project-plan-revised.md`](docs/retinode-project-plan-revised.md): the
  full design and phased plan.
- [`docs/retinode-project-plan.md`](docs/retinode-project-plan.md): the earlier draft.

## Development

Contributor setup and the load-bearing `engine/` boundary rule live in
[CONTRIBUTING.md](CONTRIBUTING.md).

The commands, with their expected output and runtimes, are in
[`docs/SETUP.md`](docs/SETUP.md); this is only the map.

Test markers: `neuron` (needs the compiled cable engine), `slow` (long NEURON or FEM
runs), and `fem` (needs a FEM backend). The fast suite excludes all three, runs on every
push, and is the only suite that needs no toolchain beyond uv. Every suite runs in CI,
on `ubuntu-latest`, which is why the macOS `nrnivmodl` defect never shows up there and
does show up for a Mac reader.

## How to cite

There is no paper and no DOI yet. If this work is useful to you, cite the repository
and the commit you ran, and say which tier produced the numbers (analytical or FEM),
since the two are not interchangeable:

> \<author\>. *Retinode: an epiretinal electrode-geometry selectivity testbed.*
> <https://github.com/hkim113005/retinode>, commit `<sha>`, \<year\>.

Two obligations are **not** optional and do not belong to this project to waive: the
Fohlmeister-Miller channel mechanisms and the mouse RGC morphology carry their own
citation requirements. See [NOTICE](NOTICE) for the exact references.

## License and credits

The code written for this project is MIT licensed; see [LICENSE](LICENSE).

Two vendored scientific assets are **excluded from that grant**. They are redistributed
under their own terms, spelled out in [NOTICE](NOTICE), and both ask to be cited if you
publish work built on them:

- The **Fohlmeister-Miller RGC channels** (`spike.mod`, `capump.mod`) come from ModelDB
  accession #3673. See `engine/cable/mechanisms/PROVENANCE.md` for the exact retrieval
  and the one documented modification (q10 temperature scaling).
- The **mouse RGC morphology** comes from NeuroMorpho.org, used verbatim. See
  `engine/cable/morphologies/PROVENANCE.md` for the cell, the publication, and why
  mouse was chosen over cat or rat.
