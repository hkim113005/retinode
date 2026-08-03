# Retinode

An epiretinal electrode-geometry selectivity testbed.

Retinode lets a user specify a hypothetical epiretinal electrode geometry and
current configuration, simulate how it activates a population of retinal
ganglion cells and their axons of passage, score its selectivity and safety,
compare it against alternatives, and export a ranked shortlist of
configurations worth testing in tissue.

The tool **screens and generates hypotheses**. It proposes configurations for
ex vivo or in vivo testing. It is not, from simulation alone, a ground-truth
oracle — every result carries its accuracy tier and its sensitivity.

> **New here?** [`docs/user-guide.md`](docs/user-guide.md) is the front-to-end
> walkthrough — install, launch the app, work through every screen, and drop to the
> code path. The rest of this README is the architecture and development reference.

## Terminology

- **Geometry** — the *physical* array: electrode sizes, shapes, positions,
  pitch, and placement. Changing geometry requires re-solving the field.
- **Configuration** (or *stimulus*) — the *current delivery*: which electrodes
  source and which return, with what weights and waveform, over a fixed
  geometry. Changing configuration is cheap — a weighted sum over an
  already-solved field.
- **Transfer matrix** — the field each electrode produces per unit current; the
  universal handoff between the field solvers and the cells.
- **Accuracy tier** — analytical, FEM, or cross-checked, attached to every number.

## Architecture

Four layers, with a strict rule: **the engine knows nothing about the
application, and the spec objects are the single source of truth.**

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

One boundary is load-bearing: **`engine/` may not import from `api/` or
`app/`.** That rule is what makes the later polished-app build a re-skin, not a
rewrite.

## Status

**Phases 1–8 complete** — from the single-configuration evaluator through to the
polished application. Retinode places biophysical (Fohlmeister–Miller) RGCs, drives
them with the array's extracellular field, finds each cell's threshold with
multi-site detection (a spike at any compartment — so an axon of passage is a
first-class off-target), and scores a **safe-and-selective operating window** with
the provenance key that identifies it. On top of that evaluator: a **FEM field tier**
(DOLFINx) for shaped/3D electrodes and geometry comparison, a **geometry-sweep study
engine** with a selectivity-versus-cost Pareto frontier, and a **FastAPI + React
application** (Compare / Study / Candidates / Validation) — see *The app* below.

The phase plans record the build step by step, with decisions and findings:

- [`docs/phase-1-plan.md`](docs/phase-1-plan.md) … [`docs/phase-8-plan.md`](docs/phase-8-plan.md) — the per-phase build logs
  ([phase-7-design.md](docs/phase-7-design.md) is the UX bar for the app;
  [phase-8-findings.md](docs/phase-8-findings.md) records the analytical-tier limits and their fix)
- [`docs/retinode-project-plan-revised.md`](docs/retinode-project-plan-revised.md) — full design and phased plan
- [`docs/retinode-project-plan.md`](docs/retinode-project-plan.md) — earlier draft

## Reproduce the headline result

One command reproduces the tool's reason for existing: **electrode geometry changes
selectivity, and only the FEM tier can see it.** Two flat disks (10 µm, 30 µm) score
*byte-identically* on the analytical tier — a point source, blind to an electrode's
extent — and *distinctly* on FEM. It checks the FEM numbers against the values recorded
in [`docs/phase-8-findings.md`](docs/phase-8-findings.md) and **exits non-zero if the
engine has drifted**, so it's a reproducibility guarantee, not a demo.

It needs the conda `retinode-fem` env (FEM + NEURON); ~1–2 minutes.

```bash
/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python examples/reproduce_headline.py
```

```
  diameter |   analytical |        FEM
-----------+--------------+-----------
      10 µm |      8.31 µA |    9.49 µA
      30 µm |      8.31 µA |   10.20 µA
✓ analytical: d10 and d30 are identical (8.31 µA) — the point source is blind to diameter
✓ FEM: d10 (9.49 µA) and d30 (10.20 µA) differ — the geometry effect the analytical tier can't see
✓ provenance: FEM numbers match the recorded headline
HEADLINE REPRODUCED ✓
```

**What "reproducible" guarantees here:** the FEM thresholds must land within ±0.30 µA of
the recorded values or the command fails; the analytical pair must be identical (the
point source is diameter-blind by construction). Results are identified by provenance
(`result_key` / `offtarget_hash`) — the engine refuses to compare across differing
off-target sets. The physical fidelity ceiling is unchanged: mouse RGC morphology,
trend-not-magnitude validation ([validation.md](docs/validation.md)).

## Development

Contributor setup, the test markers, and the load-bearing `engine/` boundary rule live
in [CONTRIBUTING.md](CONTRIBUTING.md). Retinode uses [uv](https://docs.astral.sh/uv/)
and Python 3.12.

```bash
# fast suite (no NEURON): arithmetic, evaluator logic, field, spec
uv sync --extra dev
uv run ruff check .
uv run mypy engine
uv run pytest -m "not slow and not neuron and not fem"

# NEURON tests: install the cable engine and compile the FM mechanisms first
uv sync --extra cable --extra dev
(cd engine/cable/mechanisms && uv run nrnivmodl .)
uv run pytest -m neuron
```

Test markers: `neuron` (needs the compiled cable engine), `slow` (long
NEURON/FEM runs), `fem` (needs a FEM backend). The fast suite excludes all three
and runs on every push; both suites run in CI.

### The app

A FastAPI service over the engine, with a React client. Design an array,
stimulus, and patch, watch the live field preview, and evaluate the selective
operating window without touching code:

```bash
uv sync --extra cable --extra api
uv run uvicorn api.main:create_app --factory --port 8000   # the engine, over HTTP

cd app/web && npm install && npm run dev                   # http://localhost:5173
```

Screens: **Compare** (live field, isopotential contours, scorecard, FEM tier, run
history — and a **3D electrode body**: author a pillar / dome / taper or upload a
STEP/BREP solid, scored on FEM with the real bodied field and the shape in the 3D
loupe; see [docs/custom-electrode.md](docs/custom-electrode.md)), **Study** (a
diameter × pitch sweep to a selectivity-versus-cost frontier), **Candidates** (a
charge-safe ranked shortlist, exportable), and **Validation** (what the engine
reproduces). Every plot exports as figure-quality SVG or high-DPI PNG; `⌘K` opens the
command palette.

> The Phase-2 Dash dashboard was retired in Phase 7 once the React client reached
> parity. `app/views.py` outlived it as the API's independent test oracle.
