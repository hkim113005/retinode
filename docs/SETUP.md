# Setup

The one document to follow if you have just cloned Retinode. It is organised as three
tiers, so you get a real result before committing to a heavy install. Stop wherever the
tier you reached answers your question.

| Tier | Time | What you install | What you can then do |
|---|---|---|---|
| **1** | about 5 min | uv, pure Python (numpy/scipy) | run the 449-test fast suite, lint, type-check |
| **2** | about 15 min | NEURON, node, the API and the web client | score a real operating window, in the browser |
| **3** | 30 min or more | the conda `retinode-fem` env (DOLFINx + gmsh) | FEM, 3D electrodes, and the headline reproduction |

There are exactly **two Python environments**, and that is the single thing that trips
people:

- the **uv env** (`.venv`, Python 3.12) covers Tier 1 and Tier 2: the pure engine,
  NEURON, the API, the web client;
- the **conda env `retinode-fem`** covers Tier 3, because DOLFINx ships no pip wheel
  and cannot live in the uv env. Nothing else moves between them: the app dispatches
  FEM work to the conda interpreter as a subprocess, so you never switch by hand.

## Run the doctor first

`scripts/doctor.py` is standard library only, so it runs on a bare Python 3.12 before
anything is installed. It is read only: it installs, compiles, and writes nothing.

```bash
python3 scripts/doctor.py
```

It ends with the tier summary, which is the fastest honest answer to "what works on
this machine":

```
Capability tiers
----------------
Tier 1  analytical engine + fast tests ......... AVAILABLE
        uv run python -m pytest -m "not slow and not neuron and not fem"

Tier 2  NEURON thresholds ...................... AVAILABLE
        uv run python -m pytest -m neuron

Tier 3  FEM, 3D, headline reproduction ......... AVAILABLE
        $RETINODE_FEM_PYTHON examples/reproduce_headline.py

17 passed, 0 failed, 0 skipped.
Tier 1 works, so the tool is usable.
```

Every failing check prints the exact command that fixes it. Re-run it after each tier.

## Verified on

Every command and every number below was run on this machine:

- macOS 26.5.1, Apple Silicon (`arm64`)
- uv 0.11.28, project interpreter Python 3.12.13 (uv provisions it; you do not need a
  system 3.12)
- node v22.3.0, npm 10.8.1
- conda from miniforge, `retinode-fem` with DOLFINx 0.11.0

CI runs all four jobs (fast suite, NEURON, FEM, web) on `ubuntu-latest`, so Tier 1 and
Tier 2 are also continuously verified on Linux. Nothing here has been run on Windows.

Timings come in two flavours and both are reported, because the gap is large:

- **cold** means the package manager had to download everything (measured with a
  throwaway cache directory), which is what a genuinely new machine sees;
- **warm** means the download cache already had the packages, which is what a second
  clone or a re-sync sees.

---

## Tier 1: the engine and the fast suite (about 5 minutes)

No NEURON, no conda, no node. Pure numpy/scipy plus the test and cache dependencies.

```bash
git clone https://github.com/hkim113005/retinode.git
cd retinode
uv sync --extra dev --extra store --extra api
```

`dev` alone is not enough, and this is the single most common Tier 1 failure. pytest
imports **every** module under `tests/` during collection, before `-m` deselects
anything, so `tests/store` (h5py, pyarrow) and `tests/api` (fastapi, httpx) must import
even though their tests are not what you are running. See
[Troubleshooting](#a-pile-of-errors-during-collection-21-errors-during-collection).

Measured: **1 min 24 s cold**, 0.7 s warm. It resolves 54 packages and creates `.venv`
with Python 3.12.13.

Now the suite. Always invoke it as `uv run python -m pytest`, never as a bare `pytest`
([why](#bare-pytest-fails-with-a-missing-module-or-a-datetime-error)):

```bash
uv run python -m pytest -m "not slow and not neuron and not fem" -q
```

```
449 passed, 11 skipped, 67 deselected, 1 warning in 4.37s
```

The 11 skips are the DOLFINx test modules, which skip cleanly at import because there
is no FEM backend in this env yet. That is expected at Tier 1, not a problem. The 67
deselected are the NEURON tests, which Tier 2 turns on.

The other two CI gates, if you want the full green:

```bash
uv run ruff check .        # All checks passed!
uv run mypy engine         # Success: no issues found in 68 source files
```

### What Tier 1 proves, and what it does not

**Proves:** the engine imports and its arithmetic is right. The spec layer's validation,
canonicalization, and hashing; the analytical field solver and the transfer-matrix
contract; the evaluator's operating-window algebra; the Shannon and charge-density
safety criteria; the study and sweep bookkeeping; the store's cache keys and provenance
records; the FastAPI request and response contract against `app/views.py` as an
independent oracle; and the load-bearing rule that `engine/` never imports from `api/`
or `app/` (`tests/api/test_boundary.py` scans for it).

**Does not prove:** anything biophysical or geometric. No cell was simulated, because
NEURON is not installed. No electrode geometry was resolved, because the analytical
tier is a point source that cannot see an electrode's size or shape. Every threshold in
the fast suite comes from an injected fake threshold provider, so a green Tier 1 says
the plumbing is correct, not that the physics is.

---

## Tier 2: NEURON, the API, and the browser (about 15 minutes)

This is where cells actually spike. Add the `cable` extra and compile the
Fohlmeister-Miller mechanisms once.

```bash
uv sync --extra cable --extra dev --extra store --extra api
(cd engine/cable/mechanisms && uv run nrnivmodl .)
```

`nrnivmodl` should end with:

```
Successfully created arm64/special
```

(`x86_64/special` on an Intel Mac or on Linux). The `Notice:` and `Warning:` lines above
it, about VERBATIM blocks, CVODE, and PARAMETER defaults being set by NEURON, are the
mechanism translator's normal chatter, not errors. Compiling takes a few seconds.

Confirm the engine can load it:

```bash
uv run python -c "import neuron; print('neuron ok', neuron.__version__)"
```

```
Warning: no DISPLAY environment variable.
--No graphics will be displayed.
neuron ok 9.0.1
```

The DISPLAY warning is NEURON announcing it has no GUI. It is harmless and appears on
every headless run.

### If `nrnivmodl` fails on macOS, read this

This is the trap that costs people the most time, so it is here and not in a footnote.

On this machine the plain command above works with the PyPI `neuron` 9.0.1 wheel. It
does not always. The macOS wheel can bake its **build-time temporary prefix** into its
build files instead of its install path, and then `nrnivmodl` fails with one of:

```
FileNotFoundError: .../Applications/NEURON/...
No rule to make target '/var/folders/.../wheel/platlib/bin/nrnmech_makefile'
```

`import neuron` still works when this happens. Only the compile tooling is broken. The
fix repoints the prefix in the two **text** build files (never the `.dylib` or `.a`
binaries) and then compiles with the real binary rather than the wrapper:

```bash
DATA="$PWD/.venv/lib/python3.12/site-packages/neuron/.data"
TMP=$(grep -oE '/var/folders/[^"'"'"' ]*/wheel/platlib' "$DATA/bin/nrnivmodl" | head -1)
perl -pi -e "s|\Q$TMP\E|$DATA|g" "$DATA/bin/nrnivmodl" "$DATA/include/nrnconf.h"
(cd engine/cable/mechanisms && uv run --extra cable "$DATA/bin/nrnivmodl" .)
```

Verified: run from the repository root, this prints the same
`Successfully created arm64/special`, and the compiled mechanisms then pass the NEURON
suite.

**Do not use `$TMP` to decide whether you need the patch.** On a fresh `neuron` 9.0.1
install on this machine `$TMP` is *not* empty, and the plain `uv run nrnivmodl .` works
anyway: `uv run` invokes `.venv/bin/nrnivmodl`, a Python wrapper that works out its own
paths, whereas the stale prefix sits in `.../site-packages/neuron/.data/bin/nrnivmodl`,
which that wrapper never reads. An empty `$TMP` is also exactly what an already-patched
`.venv` looks like, so the grep cannot tell "no defect" from "already fixed". The only
reliable test is the compile itself: run the plain command first, and reach for the
patch only if it fails.

Two things to know about the patch. It edits `.venv/`, which is not version controlled,
so **any `uv sync` that reinstalls `neuron` undoes it**; just run it again. And CI never
hits the problem, because CI is Linux.

### Run the NEURON suite

```bash
uv run python -m pytest -m neuron -q
```

```
67 passed, 11 skipped, 449 deselected, 1 warning in 734.46s (0:12:14)
```

That is **12 minutes**, and it is the long pole of Tier 2, because every one of those
tests is a real multi-compartment threshold search. For a quicker signal that the
mechanisms loaded, drop the slow ones:

```bash
uv run python -m pytest -m "neuron and not slow" -q     # 56 passed in 485.41s (8:05)
```

Neither is required to use the tool. If you are impatient, skip straight to the app
below; a scorecard that returns a number is the same proof, in 14 seconds.

### Launch the API and the web client

Two terminals. Start the API first, because the dev client proxies `/api` to port 8000.

```bash
# terminal 1, from the repository root
uv run uvicorn api.main:create_app --factory --port 8000
```

```
INFO:     Started server process [96875]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

Check it:

```bash
curl -s http://localhost:8000/health      # {"status":"ok"}
```

```bash
# terminal 2
npm --prefix app/web install
npm --prefix app/web run dev
```

```
  VITE v5.4.21  ready in 181 ms

  ➜  Local:   http://localhost:5173/
```

`npm install` measured **50 s cold**, 3.8 s warm. Open <http://localhost:5173>. The
Compare screen loads with a blue analytical field heatmap and an "Analytical" tier chip.

### Score a real operating window

In the browser: leave the defaults (single flat 10 µm disk, 200 µs cathodic pulse,
neighbour at 40 µm, sigma = 1 S/m) and click **Run scorecard**. It takes about 15
seconds, because a NEURON threshold search runs for the target and for the bystander.

The same thing from the shell, if you want the raw numbers:

```bash
curl -s -X POST http://localhost:8000/score \
  -H 'content-type: application/json' -d '{"electrode_um":10.0}'
# -> {"id": "...", "status": "running", ...}; poll GET /jobs/{id}
```

Measured, 14 s, the job comes back `done` with:

```json
{
  "activated": true,
  "target_uA": 8.3056640625,
  "off_min_uA": 12.814453125,
  "ratio": 1.542857142857143,
  "window_lo_uA": 8.3056640625,
  "window_hi_uA": 12.814453125,
  "usable_margin_uA": 4.5087890625,
  "usable": true,
  "limiting": "off_target",
  "safety_ceiling_uA": 24.918101183923635,
  "safe_at_target": true,
  "limiting_off_id": "neighbor"
}
```

Read that as: the target fires at **8.31 µA**, the bystander at **12.81 µA**, so the
usable window is **4.51 µA** wide and what closes it is the bystander, not the charge
ceiling (`"limiting": "off_target"`). Those are real Fohlmeister-Miller thresholds from
a multi-compartment cell, on the analytical field tier.

### What Tier 2 proves, and what it does not

**Proves:** the biophysics runs end to end. Cells are built and placed, the
extracellular field drives them, the threshold search brackets and bisects a real
activation threshold, spikes are detected at every compartment (so an axon of passage
is a first-class off-target), and the operating window and its limiting factor come out
the far end, over HTTP, into a browser.

**Does not prove:** anything about electrode **geometry**. Everything at Tier 2 runs on
the analytical tier, which is a point source in a homogeneous half-space. It is blind
to an electrode's diameter, its shape, and its 3D body. Change the disk from 10 µm to
30 µm at Tier 2 and the numbers do not move at all. That is the whole reason Tier 3
exists.

---

## Tier 3: the FEM environment and the headline result (30 minutes or more)

DOLFINx has no pip wheel, so this is a second, conda-forge environment. It is the heavy
one: budget half an hour or more for the solve, mostly conda dependency resolution.

```bash
conda env create -f env/fem-environment.yml   # creates `retinode-fem`
conda activate retinode-fem
pip install -e . --no-deps                    # so `import engine` works there
```

`--no-deps` matters. Conda already supplies the scientific stack, and letting pip
resolve it again can shadow the conda builds.

Check the env:

```bash
FEMPY=/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python
$FEMPY -c "import dolfinx, gmsh, neuron; print('fem env ok', dolfinx.__version__)"
```

```
numprocs=1
fem env ok 0.11.0
```

`numprocs=1` is NEURON reporting its MPI rank count on import. Also confirm the project
itself is importable there, which is what `pip install -e . --no-deps` bought you:

```bash
$FEMPY -c "import engine, api, app; print('engine ok')"    # engine ok
```

If your conda lives somewhere else, point the app at it and use the same interpreter
for `FEMPY`:

```bash
export RETINODE_FEM_PYTHON=/path/to/envs/retinode-fem/bin/python
```

You never have to activate this env to use the app. The API finds that interpreter and
dispatches FEM jobs to it as a subprocess.

### Reproduce the headline

This is the scientific payoff, and the reason the tool exists: **electrode geometry
changes selectivity, and only the FEM tier can see it.**

```bash
$FEMPY examples/reproduce_headline.py
```

Measured: **56 s**, exit code 0. It prints about 320 lines, nearly all of them gmsh
`Info :` mesh statistics. The part that matters is the last dozen:

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

Note that the analytical 8.31 µA is the same number you got from the Tier 2 scorecard,
for both diameters. That is the point.

This is a regression gate, not a demo. The FEM thresholds must land within ±0.30 µA of
the values recorded in [`phase-8-findings.md`](phase-8-findings.md) or the script
**exits non-zero**. What the tolerance is and is not, and the four caveats that come
with the result, are spelled out in the README's
[Reproduce the headline result](../README.md#reproduce-the-headline-result). Read them
before quoting the numbers. In short: the search is deterministic, so the band is a
drift tripwire rather than an error bar; the absolute gap is small; and CI does not run
this script, which is exactly why it is one command a human can run.

### The rest of Tier 3

With the FEM env in place, the 3D electrode path opens up: pillars, domes, tapers, and
uploaded STEP or BREP solids, all scored on the real bodied field.

```bash
$FEMPY examples/custom_3d_electrode.py       # score your own 3D body in code
```

Measured: **30 s**, exit code 0. It scores a flat 10 µm disk (target 9.49 µA, window
4.75 µA), then the same-footprint 30 µm pillar twice: refused under the `reject` overlap
policy, then scored under `displace` (target 7.83 µA, window 6.05 µA). Edit the
`custom_pillar()` body to your own dimensions.

The FEM test suite runs from an activated env, scoped to `tests/field` because that is
where every `fem`-marked test lives:

```bash
conda activate retinode-fem
pytest tests/field -m fem -q                 # 37 passed, 48 deselected in 249.75s (4:09)
```

For the full pass/fail walkthrough of a new 3D design, from a cold environment to a
scored and interpreted result, follow
[`testing-a-3d-design.md`](testing-a-3d-design.md).

---

## Troubleshooting

Run `python3 scripts/doctor.py` first. It catches most of this and prints the fixing
command. What follows is the detail behind the failures that are not self-explanatory.

| Symptom | Cause | Fix |
|---|---|---|
| `21 errors during collection` on the fast suite | synced without `store` and `api` | `uv sync --extra dev --extra store --extra api` |
| bare `pytest` fails immediately | it resolved to a conda base Python | `uv run python -m pytest ...` |
| `nrnivmodl` cannot find a makefile or a NEURON prefix | the macOS wheel baked in its build-time temp path | [the perl patch above](#if-nrnivmodl-fails-on-macos-read-this) |
| a threshold search errors about a missing mechanism | mechanisms not compiled | `(cd engine/cable/mechanisms && uv run nrnivmodl .)` |
| `ModuleNotFoundError: dolfinx` running a script | you ran a FEM script in the uv interpreter | run it with `$FEMPY` |
| "the FEM env is not available" on a 3D or Study job | no conda `retinode-fem` | create it, or `export RETINODE_FEM_PYTHON=...` |
| `address already in use` starting uvicorn | port 8000 is taken | kill the old server, or use another port |
| the app loads but every request fails | the API is not running on 8000 | start uvicorn first; `curl -s http://localhost:8000/health` |
| `OverlapConflict` scoring a tall electrode | the body penetrates a cell, under the `reject` policy | intended? use `displace`. Otherwise shorten or move the body |
| a shaped electrode scores the same as a flat one | you are on the analytical tier | it cannot see geometry; the UI forces FEM for a body |

### A pile of errors during collection (`21 errors during collection`)

```
ERROR tests/api/test_body_contract.py
...
ERROR tests/store/test_fields.py
E   ModuleNotFoundError: No module named 'h5py'
!!!!!!!!!!!!!!!!!!! Interrupted: 21 errors during collection !!!!!!!!!!!!!!!!!!!
```

You synced with `--extra dev` only. pytest imports every module under `tests/` while
collecting, before `-m` gets a chance to deselect anything, so the API and store test
modules must import even when their tests will not run. The minimum for the fast suite
is:

```bash
uv sync --extra dev --extra store --extra api
```

### Bare `pytest` fails with a missing module or a datetime error

```
$ pytest -m "not slow and not neuron and not fem" -q
E   ModuleNotFoundError: No module named 'hypothesis'
Interrupted: 24 errors during collection
```

Check what you actually ran:

```bash
$ which pytest
/opt/homebrew/Caskroom/miniforge/base/bin/pytest
$ pytest --version
pytest 9.0.3
Python 3.10.19
```

That is a conda base Python on the PATH, not the project's `.venv`, and it has none of
the project's dependencies. On Python 3.10 you may instead see a failure on
`datetime.UTC`, which needs 3.11 or newer. Either way the fix is the same, and it is
why every command in this document is written the long way:

```bash
uv run python -m pytest -m "not slow and not neuron and not fem" -q
```

Note that `uv run pytest` is usually fine too, but `uv run python -m pytest` is the form
that cannot be captured by a stray `pytest` on the PATH.

### Port 8000 is already in use

```
ERROR:    [Errno 48] error while attempting to bind on address ('127.0.0.1', 8000): address already in use
```

uvicorn prints `Application startup complete` **before** this line, which makes it easy
to miss and to believe the server started. It did not. Find and stop the old one:

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
kill <pid>
```

Or run on another port, and remember that the dev client's proxy is hard-wired to 8000
in `app/web/vite.config.ts`, so if you move the API you must move the proxy target too.

### Port 5173 is already in use

Vite does not fail here, it relocates, which is friendlier and more confusing:

```
Port 5173 is in use, trying another one...

  VITE v5.4.21  ready in 188 ms

  ➜  Local:   http://localhost:5174/
```

Read the banner and open the port it actually printed. The `/api` proxy still points at
8000 from either port, so the app works fine on 5174; the only failure mode is having
two clients open and wondering which one you are looking at.

### The FEM env is missing

A 3D body or a geometry study fails the job with:

```
the FEM env is not available (scoring a 3D electrode needs DOLFINx);
set RETINODE_FEM_PYTHON or install env/fem-environment.yml
```

This is a correct refusal, not a crash. The analytical tier cannot represent a bodied
electrode, and the tool will not hand you a number it cannot vouch for. Either build the
Tier 3 env, or point `RETINODE_FEM_PYTHON` at an existing one, and restart the API so it
picks up the variable.

### `OverlapConflict` on a tall electrode

Scoring a 30 µm pillar under the default `reject` overlap policy fails the job with:

```
engine.eval.overlap.OverlapConflict: cell 'target' has 2 compartment(s) inside an
electrode body; move the cell, resize the electrode, or use the 'displace' overlap policy
```

**This is correct behaviour, not a bug.** The default target soma sits about 20 µm above
the array plane, so a 30 µm body physically passes through it. There is no extracellular
potential inside metal, so a threshold for a cell embedded in the electrode would be
meaningless. `reject` refuses instead of returning a silently wrong number.

If the penetration is what you meant to model, switch **Cell overlap** to `displace`,
which severs the compartments inside the metal and scores the rest. Verified: the same
pillar that fails under `reject` scores under `displace` in 21 seconds, giving a target
threshold of 7.83 µA and a 6.05 µA window, against 8.31 µA and 4.51 µA for the flat disk
of the same footprint. That difference is the geometry effect. Otherwise, shorten the
body or move the cell plane.

---

## What to read next

- [`user-guide.md`](user-guide.md): the front-to-end walkthrough of every screen
- [`testing-a-3d-design.md`](testing-a-3d-design.md): a pass/fail runbook for putting a
  new 3D design through the whole stack
- [`electrode-geometry.md`](electrode-geometry.md) and
  [`custom-electrode.md`](custom-electrode.md): the geometry and 3D/CAD references
- [`validation.md`](validation.md): what the engine reproduces, and how closely
- [`../README.md`](../README.md): what is actually being solved, the architecture, and
  the limits
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md): the contributor workflow and the checks CI
  runs
