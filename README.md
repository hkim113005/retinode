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

> **New here?** [`docs/user-guide.md`](docs/user-guide.md) is the front-to-end
> walkthrough: install, launch the app, work through every screen, then drop down to
> the code path. The rest of this README is the architecture and development
> reference.

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
- **Every number carries its accuracy tier** (analytical, FEM, or cross-checked) and
  its sensitivity. Treat the comparison between two designs as the signal, not either
  absolute number.
- **The analytical tier is a point source**, blind to an electrode's size and shape.
  Any question in which the geometry itself is the variable is FEM-only
  ([docs/phase-8-findings.md](docs/phase-8-findings.md)).
- **No novel design finding yet.** The headline below is a *capability* result: the
  engine resolves a geometry effect the cheap tier cannot see. Which geometries
  dominate the frontier, and why, is still open.

## Install

Retinode uses [uv](https://docs.astral.sh/uv/) and Python 3.12. The engine core is
numpy/scipy only, so everything heavy is an opt-in extra.

```bash
git clone https://github.com/hkim113005/retinode.git
cd retinode
uv sync --extra cable --extra api                    # NEURON + the API server
(cd engine/cable/mechanisms && uv run nrnivmodl .)   # compile the NEURON mechanisms once
```

Add `--extra dev` to run the tests and `--extra store` for the HDF5/parquet caches.

FEM work (shaped or 3D electrodes, geometry comparison, geometry studies) needs a
second environment, because DOLFINx ships no pip wheel. The conda `retinode-fem` env is
the one place that has DOLFINx, gmsh, and NEURON together:

```bash
conda env create -f env/fem-environment.yml   # creates `retinode-fem`
conda activate retinode-fem
pip install -e . --no-deps                    # so `import engine` works; conda supplies the deps
```

The app looks for that interpreter at the default miniforge path and dispatches FEM
jobs to it as a subprocess, so you never switch environments by hand. If yours lives
elsewhere, point the app at it with
`export RETINODE_FEM_PYTHON=/path/to/envs/retinode-fem/bin/python`. Skip this env
entirely if you only need the analytical tier (flat disks, single configurations); the
app says plainly when a request requires FEM.

## Run the app

A FastAPI service over the engine, with a React client. Design an array, stimulus, and
patch, watch the live field preview, and evaluate the selective operating window
without touching code:

```bash
uv run uvicorn api.main:create_app --factory --port 8000   # the engine, over HTTP

cd app/web && npm install && npm run dev                   # http://localhost:5173
```

Start the server first: the dev client proxies `/api` to port 8000.

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

It needs the conda `retinode-fem` env (FEM + NEURON) and takes ~1–2 minutes.

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
differing off-target sets. The physical fidelity ceiling is unchanged: mouse RGC
morphology, trend-not-magnitude validation ([docs/validation.md](docs/validation.md)).

## Terminology

- **Geometry**: the *physical* array, meaning electrode sizes, shapes, positions,
  pitch, and placement. Changing geometry requires re-solving the field.
- **Configuration** (or *stimulus*): the *current delivery*, meaning which electrodes
  source and which return, with what weights and waveform, over a fixed geometry.
  Changing configuration is cheap, a weighted sum over an already-solved field.
- **Transfer matrix**: the field each electrode produces per unit current, and the
  universal handoff between the field solvers and the cells.
- **Accuracy tier**: analytical, FEM, or cross-checked, attached to every number.
- **Off-target** (or *bystander*): any cell or axon of passage that should stay silent.
  A spike anywhere on it closes the operating window.

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

## Status

**Phases 1–8 complete**, from the single-configuration evaluator through to the
polished application, and Phase 9 (packaging, docs, and the one-command reproduction)
has landed. Retinode places biophysical (Fohlmeister–Miller) RGCs, drives them with the
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

Contributor setup, the test markers, and the load-bearing `engine/` boundary rule live
in [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
# fast suite (no NEURON): arithmetic, evaluator logic, field, spec.
# store + api are needed even here: pytest imports EVERY module under tests/ during
# collection, before -m deselects anything, so tests/api and tests/store must import.
uv sync --extra dev --extra store --extra api
uv run ruff check .
uv run mypy engine
uv run pytest -m "not slow and not neuron and not fem"

# NEURON tests: install the cable engine and compile the FM mechanisms first
uv sync --extra cable --extra dev --extra store --extra api
(cd engine/cable/mechanisms && uv run nrnivmodl .)
uv run pytest -m neuron
```

Test markers: `neuron` (needs the compiled cable engine), `slow` (long NEURON or FEM
runs), and `fem` (needs a FEM backend). The fast suite excludes all three and runs on
every push; every suite runs in CI.

## License and credits

The code written for this project is MIT licensed; see [LICENSE](LICENSE).

Two vendored scientific assets are **excluded from that grant**. They are redistributed
under their own terms, spelled out in [NOTICE](NOTICE), and both ask to be cited if you
publish work built on them:

- The **Fohlmeister–Miller RGC channels** (`spike.mod`, `capump.mod`) come from ModelDB
  accession #3673. See `engine/cable/mechanisms/PROVENANCE.md` for the exact retrieval
  and the one documented modification (q10 temperature scaling).
- The **mouse RGC morphology** comes from NeuroMorpho.org, used verbatim. See
  `engine/cable/morphologies/PROVENANCE.md` for the cell, the publication, and why
  mouse was chosen over cat or rat.
