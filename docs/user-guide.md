# Retinode user guide

How to use Retinode front to end: install it, launch the app, walk a design from a
blank Compare screen to an exported shortlist, and drop down to the code path when you
need to script or sweep. This is the practical "how do I actually use this" guide; for
the *why* and the physics, follow the links at the end.

## What Retinode is (and isn't)

Retinode is an **epiretinal electrode-geometry selectivity testbed**. You describe a
hypothetical electrode geometry and a current configuration; it places a population of
retinal ganglion cells (RGCs) and their axons of passage, drives them with the array's
extracellular field, finds each cell's activation threshold, and scores a
**safe-and-selective operating window** — how much you can turn the amplitude up before
a *bystander* fires or you cross a charge-safety limit.

It **screens and generates hypotheses** — configurations worth testing ex vivo / in
vivo. It is not, from simulation alone, a ground-truth oracle: every number carries its
**accuracy tier** (analytical / FEM / cross-checked) and its sensitivity. Treat the
*comparison* between two designs as the signal, not either absolute number.

The two words to keep straight ([README](../README.md) has the full glossary):

- **Geometry** — the physical array (sizes, shapes, positions, pitch, 3D bodies).
  Changing it means re-solving the field.
- **Configuration / stimulus** — the current delivery (which electrodes source/return,
  weights, waveform) over a fixed geometry. Cheap to change — a weighted sum over an
  already-solved field.

## The two environments (read this first)

Retinode runs across **two Python environments**, and knowing which does what saves a
lot of confusion:

| Environment | Has | Does |
|---|---|---|
| **`uv`** (Python 3.12) | analytical field, NEURON (`--extra cable`), FastAPI (`--extra api`) | the app server, the fast analytical field, NEURON threshold searches, everything except FEM |
| **conda `retinode-fem`** | DOLFINx + gmsh **and** NEURON | the FEM field tier — shaped/3D electrodes, geometry comparison, "Run accurately" |

**Why two:** DOLFINx (the FEM solver) installs cleanly only through conda; NEURON and
the rest install through `uv`. The `retinode-fem` conda env is the one place that has
*both*, so FEM work happens there. The app runs in the `uv` env and **dispatches** any
FEM job to the conda interpreter as a subprocess — you don't switch environments by
hand, but the conda env must exist for anything FEM (a 3D electrode, "Run accurately",
a geometry study).

**The analytical tier is a point source.** It is blind to an electrode's size and
shape — two different diameters produce byte-identical fields. So any question where the
geometry itself is the variable (a shaped electrode, comparing diameters) is
**FEM-only**. Flat-disk single-configuration questions run fine on the fast analytical
tier.

## Setup

Retinode uses [uv](https://docs.astral.sh/uv/) and Python 3.12.

### 1. The `uv` environment (always needed)

```bash
uv sync --extra cable --extra api    # NEURON + the API server
# compile the NEURON mechanisms once (needed for threshold searches):
(cd engine/cable/mechanisms && uv run nrnivmodl .)
```

Add `--extra dev` if you'll run the test suite, `--extra store` for the HDF5/parquet
caches.

### 2. The conda FEM environment (needed for FEM / 3D / studies)

```bash
# with conda/miniforge installed:
conda env create -f env/fem-environment.yml     # creates `retinode-fem`
```

The app finds this interpreter at the default miniforge path
(`/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python`). If yours lives
elsewhere, point the app at it:

```bash
export RETINODE_FEM_PYTHON=/path/to/envs/retinode-fem/bin/python
```

You can skip step 2 if you only need the analytical tier (flat disks, single
configurations). The app will tell you clearly if you ask for FEM without the env.

### 3. The web client

```bash
cd app/web && npm install
```

## Launching the app

The app is a **FastAPI service** (the engine over HTTP) plus a **React client**. Start
both:

```bash
# terminal 1 — the API (uv env)
uv run --extra api --extra cable uvicorn api.main:create_app --factory --port 8000

# terminal 2 — the web client
npm --prefix app/web run dev        # http://localhost:5173
```

Then open **http://localhost:5173**. (If you use the editor's launch panel, the `api`
and `web` targets in `.claude/launch.json` do the same thing.)

A quick check that the API is up: `curl http://localhost:8000/health` → `{"status":"ok"}`.

## Using the app, screen by screen

The left rail navigates four screens. A typical session runs left to right: **design
one electrode (Compare) → sweep a family (Study) → shortlist the winners (Candidates) →
sanity-check what the engine reproduces (Validation)**. `⌘K` opens a command palette for
everything.

### Compare — design and score one configuration

The working screen. The right-hand **control rail** sets the geometry and stimulus; the
field redraws live.

- **Return** — Monopolar (a distant return) or Bipolar (a local return, with a pitch).
- **Electrode diameter, neighbour distance, phase width, tissue conductivity** — sliders
  over the ranges the engine was exercised on.
- **Electrode body** — Flat (a plain disk) or a 3D shape: **Dome / Pillar / Taper**, or
  a **CAD** upload (STEP/BREP). Bodies have dimension inputs, a conductive-faces
  selector (tip / sides / all), and a cell-overlap policy (see below).

What you get:

- **Live field** — the extracellular potential on the cell plane, with labelled
  isopotential contours; hover for a readout. The target cell is the filled marker, the
  bystander the open one. A docked **3D loupe** (bottom-right, click to expand) shows the
  array, the tissue slab, and the cells — and the true 3D electrode body if you set one.
- **Scorecard** (right, *Run scorecard*) — the operating window. Because it needs a
  NEURON threshold search (seconds, not milliseconds), it runs as a background job.
- **Accuracy tier** — starts **Analytical** (the fast preview). *Run accurately (FEM)*
  dispatches the field to the conda env and re-badges it **FEM**, with a note on how far
  the accurate field moved from the preview.
- **Activation vs amplitude** (*Sweep amplitudes*) — instead of just the threshold
  crossing, the whole ladder: who joins next as current rises, and whether anyone stops
  firing again.
- **Run history** — each scored configuration is remembered so two designs sit side by
  side. The engine refuses to compare two runs measured against *different* bystander
  sets — a category error it flags rather than lets you misread.

**3D electrodes are FEM-only.** The moment you pick a body, the live analytical field is
replaced by a **"3D — FEM required"** prompt (the point source can't represent geometry).
*Run field (FEM)* and *Run scorecard* then dispatch to the conda env and return the real
bodied field (with a hole where the metal sits) and the operating window. A penetrating
body reaches the cell plane, so you choose an **overlap policy**: *reject* (refuse to
score a cell embedded in metal — the safe default) or *displace* (sever the in-metal
compartments and score the rest). Full walkthrough:
[custom-electrode.md](custom-electrode.md).

### Study — sweep a family to a frontier

Pick a set of **diameters × pitches**; Study scores every combination (dropping ones
where pitch < diameter, which would overlap) and plots them on a **selectivity-versus-
cost Pareto frontier**. Click a frontier point to inspect its geometry and metrics.
Optionally raise the **trajectory count** to measure robustness — the spread of the
target threshold over several jittered axon trajectories, drawn as an error bar.

A study is a real FEM sweep (geometry is the variable, so it must be FEM), dispatched to
the conda env — minutes, with a live progress bar. It needs the conda env; without it,
the job fails with a clear message rather than a degenerate flat frontier.

### Candidates — the shortlist to test

The payoff: a **ranked, charge-safe shortlist** of the designs worth testing in tissue —
each with its threshold, selective window, charge verdict, accuracy tier, and a one-line
rationale. Sort by window, cost, or **Robustness** (only offered when the study actually
measured a trajectory spread — it won't invent an order for an unmeasured column).
**Export** the shortlist for the lab. Brush a corner of the frontier and the superlatives
rename themselves to the brushed scope ("the widest window *in this selection*"), never
overclaiming.

### Validation — what the engine reproduces

Not a design surface — the honesty ledger. It lists the published/analytical results the
engine reproduces and how closely (the same report [validation.md](validation.md)
describes), so you can see what the tool has been checked against before trusting a
number.

## The code path (scripting, sweeps, repro)

Everything the app does is a thin layer over the `engine` library. Reach for code when
you want reproducibility, parameter sweeps, a custom patch, or capabilities the rail
doesn't expose (array tilt, bipolar bodies). The core call is `evaluate`:

```python
from app.scene import build_scene            # controls -> the four spec objects
from engine.eval import evaluate
from engine.field import AnalyticalBackend

scene = build_scene(
    layout="single", electrode_um=10.0, pitch_um=60.0,
    phase_width_us=200.0, neighbor_um=40.0, sigma_S_per_m=1.0,
)
result = evaluate(
    scene.patch, scene.array, scene.config, scene.conductivity,
    backend=AnalyticalBackend(),             # or a FenicsxBackend for FEM
)
w = result.window
print(w.target_uA, w.usable_margin_uA, w.limiting)   # threshold, headroom, what caps it
```

- **Flat disk, analytical** runs in the `uv` env (fast). **Shaped/3D electrodes** need
  `engine.field.fem_fenicsx.FenicsxBackend` and the **conda env** — run the script with
  the `retinode-fem` interpreter. The runnable, verified example is
  [`examples/custom_3d_electrode.py`](../examples/custom_3d_electrode.py):

  ```bash
  /opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python examples/custom_3d_electrode.py
  ```

- **Geometry sweeps** — `engine.study.geometry_sweep.geometry_sweep(...)` scores a grid
  to a Pareto frontier (what the Study screen calls). It routes geometry-varying sweeps
  to FEM automatically.
- **Reading the result** — `result.window` is the operating window (`target_uA`,
  `usable_margin_uA`, `safety_ceiling_uA`, `limiting`); `result.thresholds` holds the
  per-cell thresholds; `result.activated` is `False` when the target never fired.
  `result.offtarget_hash` is the provenance key that decides whether two results are even
  comparable.

The architecture boundary that makes this safe: **`engine/` never imports `api/` or
`app/`** — the library is usable on its own, and the app is a re-skin over it.

## Reproduce the headline result

One command reproduces the tool's reason for existing — that geometry changes
selectivity and only FEM sees it — and **fails if the engine has drifted** from the
recorded numbers:

```bash
/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python examples/reproduce_headline.py
```

It scores a 10 µm and a 30 µm flat disk: identical on the analytical tier (8.31 µA both
— the point source is diameter-blind), distinct on FEM (9.49 vs 10.20 µA), and checks
those FEM numbers against the values in [phase-8-findings.md](phase-8-findings.md)
within ±0.30 µA. Needs the conda `retinode-fem` env; ~1–2 minutes. See the README for
the full output and what "reproducible" guarantees.

## Reading the numbers honestly

- **Operating window** — the usable headroom above the target's threshold before a
  **bystander** fires (`limiting = "off_target"`) or the **charge-density ceiling**
  binds (`limiting = "safety"`). Bigger is more selective.
- **Accuracy tier** travels with every number. Analytical is a fast point-source
  approximation (geometry-blind); FEM is the real tissue-minus-electrode solve;
  cross-checked means two independent solvers agree. Don't compare an analytical number
  against a FEM one and read the difference as physics.
- **Axons of passage are first-class off-targets.** Threshold detection fires on a spike
  at *any* compartment, so an axon crossing under the electrode counts as activation —
  the whole point of an epiretinal selectivity tool.
- **Fidelity ceiling.** The biophysics uses a mouse RGC morphology and is validated for
  *trend, not absolute magnitude* (see Validation). 3D geometry raises *field/placement*
  fidelity, not physiological fidelity. This is a hypothesis tester, not a clinical
  predictor.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| App loads but the field is blank / API errors | the API isn't running | start uvicorn on `:8000`; check `curl :8000/health` |
| "the FEM env is not available" on a 3D/Study job | conda `retinode-fem` missing or not found | `conda env create -f env/fem-environment.yml`; set `RETINODE_FEM_PYTHON` if it's elsewhere |
| `ModuleNotFoundError: dolfinx` running a script | you're in the `uv` interpreter | run FEM scripts with the conda `retinode-fem` python |
| Threshold search errors about missing mechanisms | NEURON mechanisms not compiled | `(cd engine/cable/mechanisms && uv run nrnivmodl .)` |
| A shaped electrode gives the same numbers as a flat one | you're on the analytical tier | it can't see geometry — use FEM (the UI forces this for bodies) |
| `OverlapConflict` scoring a tall pillar | the body penetrates the cell plane | intentional? use overlap policy *displace*; otherwise shorten/move it |
| CAD upload rejected | it's an STL | STL is a surface mesh, not a solid — export STEP or BREP |

## Where to go next

- [custom-electrode.md](custom-electrode.md) — the 3D / CAD electrode how-to (UI and code)
- [electrode-geometry.md](electrode-geometry.md) — the full geometry reference (shapes, bodies, arrays, overlap)
- [validation.md](validation.md) — what the engine reproduces and how closely
- [fem-independent-checks.md](fem-independent-checks.md) — how the FEM tier is trusted
- [../README.md](../README.md) — architecture, terminology, development/test workflow
- `docs/phase-1-plan.md` … `phase-8-plan.md` — the per-phase build logs, with decisions and findings
