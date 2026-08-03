# Contributing to Retinode

Thanks for looking under the hood. This is a research testbed, so the bar is
*correctness you can trust* — every number carries its accuracy tier and its
provenance, and the tests are the contract that keeps it that way.

## Setup

Retinode uses [uv](https://docs.astral.sh/uv/) and Python 3.12. Two environments; see
[docs/user-guide.md](docs/user-guide.md) for why.

```bash
# the uv env — analytical field, NEURON, the API
uv sync --extra dev --extra cable --extra api --extra store
(cd engine/cable/mechanisms && uv run nrnivmodl .)   # compile NEURON mechanisms once

# the conda env — FEM (DOLFINx + gmsh + NEURON), only for FEM/3D/study work
conda env create -f env/fem-environment.yml
```

## The checks (what CI runs)

```bash
uv run ruff check .                                   # lint (line length 100)
uv run mypy engine                                    # types (engine is the typed core)
uv run pytest -m "not slow and not neuron and not fem"  # the fast suite — every push
uv run pytest -m neuron                               # NEURON threshold searches
# FEM tests run in the conda env:
/path/to/retinode-fem/python -m pytest tests/field -m fem
```

**Test markers.** `neuron` needs the compiled cable engine; `slow` is a long
NEURON/FEM run; `fem` needs a FEM backend (the conda env). The fast suite excludes all
three and is the gate on every push. Mark a test accurately — a `fem`/`neuron` test that
sneaks into the fast suite breaks CI on machines without those toolchains.

## The one rule that must not break

**`engine/` may not import from `api/` or `app/`.** The engine is a pure library; the
app is a re-skin over it. A CI boundary lint enforces this. It's what lets the whole
application be rebuilt without touching the science.

Corollaries you'll feel in practice:
- Spec objects (`engine/spec/`) are the single source of truth; geometry, placement, and
  overlap live in the field/spec layers, never in the cable/NEURON biophysics.
- The conda entry points (`api/*_job.py`, `api/study_core.py`, `api/scorecard_core.py`)
  are **Pydantic-free** so they import in the FEM env, which has no FastAPI.

## Conventions

- **Line length 100**, `ruff` formatted. Match the surrounding comment density and idiom.
- **Keep numbers honest.** If a result is analytical, don't imply FEM fidelity; if
  something is deferred or approximate, say so in the code and the docs. The repo has a
  habit of pinning limits with tests (see `docs/phase-8-findings.md`) so they can't be
  quietly forgotten.
- **Provenance travels with results.** A scored configuration is identified by its
  `result_key` / `offtarget_hash`; the engine refuses to compare results measured
  against different off-target sets.
- **Regenerate the contract when the API changes.** `uv run python -m api.export_schema`
  then `npm --prefix app/web run gen:types` — a snapshot test fails if they drift.

## Reproducibility

The headline result is reproducible from provenance and fails on drift — see
[README](README.md#reproduce-the-headline-result). If you change the physics, expect
`examples/reproduce_headline.py` to move; update its recorded values *and* say why in
the commit.
