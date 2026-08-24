# Retinode user guide

How to use Retinode front to end: install it, launch the app, walk a design from a
blank Compare screen to an exported shortlist, and drop down to the code path when you
need to script or sweep. This is the practical "how do I actually use this" guide. For
the *why* and the physics, follow the links at the end.

## What Retinode is (and isn't)

Retinode is an **epiretinal electrode-geometry selectivity testbed**. You describe a
hypothetical electrode geometry and a current configuration; it places a population of
retinal ganglion cells (RGCs) and their axons of passage, drives them with the array's
extracellular field, finds each cell's activation threshold, and scores a
**safe-and-selective operating window**: how far you can turn the amplitude up before a
*bystander* fires or you cross a charge-safety limit.

It **screens and generates hypotheses**, meaning configurations worth taking to an ex
vivo or in vivo experiment. From simulation alone it is not a ground-truth oracle.
Every number carries its **accuracy tier**, the field solver that produced it
(analytical or FEM), and its sensitivity. Treat the *comparison* between two designs as
the signal, not either absolute number.

For the physics itself, meaning the governing equation and boundary conditions each
tier solves, the channel model and morphology behind a threshold, the exact definition
of the operating window, and the unit and coordinate conventions, read
[What is actually being solved](../README.md#what-is-actually-being-solved) in the
README first. This guide assumes it.

Two words to keep straight ([README](../README.md) has the full glossary):

- **Geometry**: the physical array (sizes, shapes, positions, pitch, 3D bodies).
  Changing it means re-solving the field.
- **Configuration / stimulus**: the current delivery (which electrodes source and
  return, weights, waveform) over a fixed geometry. Cheap to change, because it is a
  weighted sum over an already-solved field.

## The two environments (read this first)

Retinode runs across **two Python environments**, and knowing which does what saves a
lot of confusion:

| Environment | Has | Does |
|---|---|---|
| **`uv`** (Python 3.12) | analytical field, NEURON (`--extra cable`), FastAPI (`--extra api`) | the app server, the fast analytical field, NEURON threshold searches, everything except FEM |
| **conda `retinode-fem`** | DOLFINx + gmsh **and** NEURON | the FEM field tier: shaped and 3D electrodes, geometry comparison, "Run accurately" |

**Why two.** DOLFINx (the FEM solver) installs cleanly only through conda; NEURON and
the rest install through `uv`. The `retinode-fem` conda env is the one place that has
*both*, so FEM work happens there. The app runs in the `uv` env and **dispatches** any
FEM job to the conda interpreter as a subprocess, so you never switch environments by
hand. The conda env must still exist for anything FEM: a 3D electrode, "Run
accurately", a geometry study.

**The analytical tier is a point source.** It is blind to an electrode's size and
shape, so two different diameters produce byte-identical fields. Any question where the
geometry itself is the variable (a shaped electrode, comparing diameters) is therefore
**FEM-only**. Flat-disk single-configuration questions run fine on the fast analytical
tier.

## Setup

You need [uv](https://docs.astral.sh/uv/) with Python 3.12, Node with npm for the web
client (it builds on Vite 5, so Node 18 or newer), and, for the FEM tier, conda or
miniforge. Building the NEURON mechanisms
also needs a C compiler; on macOS the Xcode command-line tools provide one
(`xcode-select --install`).

### 1. The `uv` environment (always needed)

```bash
uv sync --extra cable --extra api    # NEURON + the API server
# compile the NEURON mechanisms once (threshold searches need them):
(cd engine/cable/mechanisms && uv run nrnivmodl .)
```

Add `--extra dev` if you'll run the test suite, `--extra store` for the HDF5/parquet
caches.

Confirm it works:

```bash
uv run --extra cable python -c "import neuron; print('neuron ok')"
```

### 2. The conda FEM environment (needed for FEM, 3D, and studies)

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

Confirm it works (substitute your own path if you set the variable above):

```bash
/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python \
  -c "import dolfinx, gmsh, neuron; print('fem env ok')"
```

You can skip step 2 if you only need the analytical tier (flat disks, single
configurations). Ask for FEM without the env and the job fails with "the FEM env is not
available", which is the intended behaviour: no silent fallback to a geometry-blind
number.

### 3. The web client

```bash
npm --prefix app/web install
```

## Launching the app

The app is a **FastAPI service** (the engine over HTTP) plus a **React client**. Start
both:

```bash
# terminal 1: the API (uv env)
uv run --extra api --extra cable uvicorn api.main:create_app --factory --port 8000

# terminal 2: the web client
npm --prefix app/web run dev        # http://localhost:5173
```

Then open **http://localhost:5173**. (If you use the editor's launch panel, the `api`
and `web` targets in `.claude/launch.json` do the same thing.)

A quick check that the API is up: `curl http://localhost:8000/health` returns
`{"status":"ok"}`.

## Using the app, screen by screen

The left rail's **Analyse** group holds the four working screens: Compare, Study,
Validation, and Candidates. A typical session runs **design one electrode (Compare) →
sweep a family (Study) → shortlist the winners (Candidates) → sanity-check what the
engine reproduces (Validation)**. `⌘K` (or `Ctrl-K`) opens a command palette that
reaches every action from the keyboard.

The rail's **Design** group above it (Patch, Array, Tissue, Stimulus, Results) is a
diagram of the pipeline, not navigation. Those entries are inert by design.

### Compare: design and score one configuration

The working screen. The right-hand **control rail** sets the geometry and stimulus, and
the field redraws live.

- **Return**: Monopolar (a distant return) or Bipolar (a local return). Choosing
  Bipolar reveals the **Pair pitch** slider, which is meaningless without a return
  electrode to be pitched from.
- **Electrode diameter, Neighbour distance, Phase width, Tissue conductivity**: sliders
  over the ranges the engine was exercised on.
- **Electrode body**: Flat (a plain disk) or a 3D shape, either **Dome / Pillar /
  Taper** or a **CAD** upload (STEP/BREP). Bodies add dimension inputs, a
  conductive-faces selector (tip / sides / all), and a cell-overlap policy (see below).

What you get:

- **Live field**: the extracellular potential on the cell plane, with labelled
  isopotential contours; hover for a readout. The target cell is the filled marker, the
  bystander the open one. A docked **3D loupe** (bottom-right, click to expand) shows
  the array, the tissue slab, the cells, and the true 3D electrode body if you set one.
  Its caption names the solid it drew, so a missing or stale body is visible in text
  even if the WebGL canvas fails to paint.
- **Scorecard** (right, *Run scorecard*): the operating window. It needs a NEURON
  threshold search (seconds, not milliseconds), so it runs as a background job.
- **Accuracy tier**: starts **Analytical** (the fast preview). *Run accurately (FEM)*
  dispatches the field to the conda env and re-badges it **FEM ✓ inked**, with a note on
  how far the accurate field moved from the preview.
- **Activation vs amplitude** (*Sweep amplitudes*): instead of just the threshold
  crossing, the whole ladder, showing who joins next as current rises and whether
  anyone stops firing again.
- **Run history**: each scored configuration is remembered so two designs sit side by
  side. The engine refuses to compare two runs measured against *different* bystander
  sets. That is a category error, and it is flagged rather than left for you to
  misread.

**3D electrodes are FEM-only.** The moment you pick a body, the live analytical field is
replaced by a **"3D · FEM required"** prompt, because the point source cannot represent
geometry. *Run field (FEM)* and *Run scorecard* then dispatch to the conda env and
return the real bodied field (with a hole where the metal sits) and the operating
window. A penetrating body reaches the cell plane, so you choose a **Cell overlap**
policy: *reject* refuses to score a cell embedded in metal and is the safe default,
while *displace* severs the in-metal compartments and scores the rest. Full walkthrough:
[custom-electrode.md](custom-electrode.md).

**Uploading a CAD solid.** Pick **CAD** and choose a `.step`, `.stp`, or `.brep` file.
STEP and BREP are OpenCASCADE solids that boolean-cut cleanly; **STL is rejected by
design** because it is a surface tessellation, not a solid. The API measures the solid
once at upload time (a short subprocess in the FEM env) and caches its bounding radius,
height, and surface area beside the file, so the loupe can draw the solid's **bounding
cylinder** straight away. Without the FEM env the upload still succeeds, and the loupe
says the shape needs FEM rather than drawing a flat disk it cannot vouch for.

**CAD files are read in their own declared unit.** A STEP header declares its length
unit, and CAD packages export millimetres by default, so a millimetre STEP is converted
to microns on import. A BREP declares nothing (it is a raw geometry dump), so its
numbers are taken as microns. A solid whose bounding radius or height exceeds 2000 µm
after conversion is refused rather than solved, because at that size a wrong declared
unit is far likelier than a real retinal electrode.

### Study: sweep a family to a frontier

Pick **diameters** (8, 12, 16, 20 µm) and **pitches** (30, 40, 55, 70 µm) from the two
chip rows. Study scores every combination, drops the ones where pitch < diameter (the
electrodes would overlap), and plots the survivors on a **selectivity-versus-cost
Pareto frontier**. Click a frontier point to inspect its geometry and metrics. Switch
the **Axon-trajectory error bar** from *Off* to *Sample 3* to measure robustness: the
true axon path is unknown, so each geometry is re-scored over three jittered
trajectories and the spread is drawn as an error bar. It re-solves the field per path
and roughly quadruples the run time, which is why it is off by default.

A study is a real FEM sweep (geometry is the variable, so it must be FEM), dispatched
to the conda env, taking minutes with a live progress bar. Without the conda env the
job fails with a clear message rather than a degenerate flat frontier.

### Candidates: the shortlist to test

The payoff, a **ranked, charge-safe shortlist** of the designs worth testing in tissue,
each with its threshold, selective window, charge verdict, accuracy tier, and a
one-line rationale. Rank by **selectivity** (widest window first), **threshold**
(lowest current first), or **robustness** (tightest trajectory spread first). Robustness
is offered only when the study actually measured a spread, because sorting an unmeasured
column would invent an order. **Export list (JSON)** and **Export table (CSV)** hand the
shortlist to the lab. Brush a corner of the frontier and the superlatives rename
themselves to the brushed scope ("the widest selective window *in this selection*"),
never overclaiming.

### Validation: what the engine reproduces

Not a design surface. It is the honesty ledger, listing the published and analytical
results the engine reproduces and how closely, from the same report
[validation.md](validation.md) describes. Read it to see what the tool has been checked
against before you trust a number.

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

- **Flat disk, analytical** runs in the `uv` env (fast). **Shaped and 3D electrodes**
  need `engine.field.fem_fenicsx.FenicsxBackend` and the **conda env**, so run the
  script with the `retinode-fem` interpreter. The runnable, verified example is
  [`examples/custom_3d_electrode.py`](../examples/custom_3d_electrode.py):

  ```bash
  /opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python examples/custom_3d_electrode.py
  ```

- **Geometry sweeps**: `engine.study.geometry_sweep.geometry_sweep(...)` scores a grid
  to a Pareto frontier, which is what the Study screen calls. It routes
  geometry-varying sweeps to FEM automatically.
- **Reading the result**: `result.window` is the operating window (`target_uA`,
  `usable_margin_uA`, `safety_ceiling_uA`, `limiting`); `result.thresholds` holds the
  per-cell thresholds; `result.activated` is `False` when the target never fired.
  `result.offtarget_hash` is the provenance key that decides whether two results are
  even comparable.

The architecture boundary that makes this safe: **`engine/` never imports `api/` or
`app/`**, so the library is usable on its own and the app is a re-skin over it.

## Reproduce the headline result

One command reproduces the tool's reason for existing, that geometry changes
selectivity and only FEM sees it, and **fails if the engine has drifted** from the
recorded numbers:

```bash
/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python examples/reproduce_headline.py
```

It scores a 10 µm and a 30 µm flat disk on the shipped default scene. The tabulated
numbers are the **target cell's activation threshold**: identical on the analytical tier
(8.31 µA for both, because the point source is diameter-blind) and distinct on FEM (9.49
against 10.20 µA), checked against the values recorded in
[phase-8-findings.md](phase-8-findings.md) to within ±0.30 µA. It prints
`HEADLINE REPRODUCED ✓` and exits 0 on success, non-zero on drift. Needs the conda
`retinode-fem` env and takes 1 to 2 minutes.

Read [the README's version](../README.md#reproduce-the-headline-result) before quoting
it. It shows the full output, carries the difference through to the operating window,
and lists three things this does *not* guarantee: the ±0.30 µA band is a drift tripwire
rather than an error bar, the effect is only about three steps of the threshold search,
and CI does not run the script.

## Reading the numbers honestly

- **Operating window**: the usable headroom above the target's threshold before a
  **bystander** fires (`limiting = "off_target"`) or the **charge-density ceiling**
  binds (`limiting = "safety"`). Bigger is more selective.
- **Accuracy tier** travels with every number, and there are two: analytical, a fast
  point-source approximation that is geometry-blind, and FEM, the real
  tissue-minus-electrode solve. Don't compare an analytical number against a FEM one and
  read the difference as physics. (A third, independently cross-checked tier is designed
  but not built; see [fem-independent-checks.md](fem-independent-checks.md). The
  DOLFINx-versus-NGSolve agreement that does exist is a test the FEM tier passes, not a
  badge a result carries.)
- **Axons of passage are first-class off-targets.** Threshold detection fires on a
  spike at *any* compartment, so an axon crossing under the electrode counts as
  activation. That is the whole point of an epiretinal selectivity tool.
- **Fidelity ceiling.** The biophysics uses a mouse RGC morphology and is validated for
  *trend, not absolute magnitude* (see Validation). 3D geometry raises *field and
  placement* fidelity, not physiological fidelity. This is a hypothesis tester, not a
  clinical predictor.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| App loads but the field is blank, or the API errors | the API isn't running | start uvicorn on `:8000`; check `curl :8000/health` |
| "the FEM env is not available" on a 3D or Study job | conda `retinode-fem` missing or not found | `conda env create -f env/fem-environment.yml`; set `RETINODE_FEM_PYTHON` if it's elsewhere |
| `ModuleNotFoundError: dolfinx` running a script | you're in the `uv` interpreter | run FEM scripts with the conda `retinode-fem` python |
| Threshold search errors about missing mechanisms | NEURON mechanisms not compiled | `(cd engine/cable/mechanisms && uv run nrnivmodl .)` |
| A shaped electrode gives the same numbers as a flat one | you're on the analytical tier | it can't see geometry, so use FEM (the UI forces this for bodies) |
| `OverlapConflict` scoring a tall pillar | the body penetrates the cell plane | intentional? use Cell overlap *displace*; otherwise shorten or move it |
| CAD upload rejected | it's an STL | STL is a surface mesh, not a solid, so export STEP or BREP |
| CAD uploads but the loupe says the shape needs FEM | no FEM env at upload time, so the solid was never measured | create the conda env, then re-upload the file |
| A CAD solid is refused as implausibly large | its declared length unit is wrong (or a BREP authored in mm) | re-export at micron scale, or as a STEP that declares its unit |

## Where to go next

- [SETUP.md](SETUP.md): the tiered install, with verified output, timings, and
  troubleshooting
- [custom-electrode.md](custom-electrode.md): the 3D and CAD electrode how-to (UI and code)
- [electrode-geometry.md](electrode-geometry.md): the full geometry reference (shapes, bodies, arrays, overlap)
- [testing-a-3d-design.md](testing-a-3d-design.md): a pass/fail runbook for putting a new 3D design through the whole stack
- [validation.md](validation.md): what the engine reproduces and how closely, plus
  how the FEM tier is trusted and what is still missing from that argument
- [fem-independent-checks.md](fem-independent-checks.md): the third-party field
  cross-check (Sim4Life, COMSOL) that is designed and deliberately not built
- [../README.md](../README.md): the governing equations and units, terminology,
  architecture, and the development and test workflow
- [../CONTRIBUTING.md](../CONTRIBUTING.md): the contributor workflow and repo conventions
- `docs/phase-1-plan.md` through `phase-9-plan.md`: the per-phase build logs, with decisions and findings
