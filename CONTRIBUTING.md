# Contributing to Retinode

Thanks for looking under the hood. This is a research testbed, so the bar is
*correctness you can trust*: every number carries its accuracy tier and its provenance,
and the tests are the contract that keeps it that way.

## Setup

Retinode uses [uv](https://docs.astral.sh/uv/) and Python 3.12. There are two
environments, because DOLFINx ships no pip wheel and lives on conda-forge alone. See
[docs/user-guide.md](docs/user-guide.md) for the longer version.

```bash
# the uv env: analytical field, NEURON, the API
uv sync --extra dev --extra cable --extra api --extra store
(cd engine/cable/mechanisms && uv run nrnivmodl .)   # compile NEURON mechanisms once

# the conda env: FEM (DOLFINx + gmsh + NEURON), only for FEM, 3D, and study work
conda env create -f env/fem-environment.yml
conda activate retinode-fem
pip install -e . --no-deps                           # so `import engine` works there
```

The `--no-deps` matters: conda already supplies the scientific stack, and letting pip
resolve it again can shadow the conda builds.

## The checks (what CI runs)

```bash
uv run ruff check .                                     # lint (line length 100)
uv run mypy engine                                      # types (engine is the typed core)
uv run pytest -m "not slow and not neuron and not fem"  # the fast suite, on every push
uv run pytest -m neuron                                 # NEURON threshold searches
```

FEM tests run under the conda interpreter, scoped to `tests/field` (that is where every
`fem`-marked test lives, and it avoids collecting suites whose dependencies the FEM env
does not have):

```bash
conda activate retinode-fem
pytest tests/field -m fem
```

The React client has its own gate, run from `app/web`:

```bash
npm ci
npm run gen:types    # regenerate the TS types; CI fails if the committed ones drift
npm run typecheck
npm run test
npm run build
```

**Watch the extras.** Even the fast suite needs `store` and `api`. pytest imports every
module under `tests/` during collection, before `-m` deselects anything, so
`tests/store` (h5py, pyarrow) and `tests/api` (fastapi, httpx) must import even when
their tests never run. `uv sync --extra dev --extra store --extra api` is the minimum.

**Test markers.** `neuron` needs the compiled cable engine; `slow` is a long NEURON or
FEM run; `fem` needs a FEM backend (the conda env). The fast suite excludes all three
and is the gate on every push. Mark a test accurately: a `fem` or `neuron` test that
sneaks into the fast suite breaks CI on machines without those toolchains.

## The one rule that must not break

**`engine/` may not import from `api/` or `app/`.** The engine is a pure library and the
app is a re-skin over it. `tests/api/test_boundary.py` scans every file under `engine/`
for such an import and fails the fast suite (so, CI) if one appears. That rule is what
lets the whole application be rebuilt without touching the science.

Corollaries you will feel in practice:

- Spec objects (`engine/spec/`) are the single source of truth. Geometry, placement, and
  overlap live in the field and spec layers, never in the cable/NEURON biophysics.
- The conda entry points (`api/*_job.py`, `api/study_core.py`, `api/scorecard_core.py`)
  are **Pydantic-free** so they import in the FEM env, which has no FastAPI.

## Conventions

- **Line length 100**, `ruff` formatted. Match the surrounding comment density and idiom.
- **Keep numbers honest.** If a result is analytical, do not imply FEM fidelity. If
  something is deferred or approximate, say so in the code and in the docs. The repo has
  a habit of pinning limits with tests (see [docs/phase-8-findings.md](docs/phase-8-findings.md))
  so they cannot be quietly forgotten.
- **Provenance travels with results.** A scored configuration is identified by its
  `result_key` / `offtarget_hash`, and the engine refuses to compare results measured
  against different off-target sets.
- **Regenerate the contract when the API changes.** Run `uv run python -m api.export_schema`,
  then `npm --prefix app/web run gen:types`. A snapshot test fails if the two drift apart.
- **Record the reasoning, not just the change.** Decisions, rejected alternatives, and
  known limits belong in the phase docs and in the commit message. That record is the
  most useful thing in this repo.

## Reproducibility

The headline result is reproducible from provenance and fails on drift; see
[README](README.md#reproduce-the-headline-result). If you change the physics, expect
`examples/reproduce_headline.py` to move. Update its recorded values *and* say why in
the commit.

## Before you open a pull request

- The fast suite, `ruff`, and `mypy` pass locally, plus the `neuron` suite if you
  touched the cable layer and the `fem` suite if you touched a field backend.
- New or changed behaviour is covered by a test, and a known limit is pinned by one.
- Docs that state a number or a command still match the code. Nothing in this repo
  should assert something the code does not do.
