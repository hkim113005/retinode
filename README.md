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
engine/   # pure library; no fastapi, no plotly, no dash imports
  spec/       # domain model, validation, serialization, hashing
  field/      # transfer-matrix contract + backends
  cable/      # NEURON population + threshold search
  eval/       # the fixed evaluator
  study/      # sweep + surrogate + cost model
  store/      # cache, project store, provenance
  validate/   # property tests, cross-backend, reproductions
api/      # FastAPI; imports engine, never the reverse
app/      # dashboard (Phase 2) then React client (Phase 6)
tests/
docs/
```

One boundary is load-bearing: **`engine/` may not import from `api/` or
`app/`.** That rule is what makes the later polished-app build a re-skin, not a
rewrite.

## Status

Early scaffolding. See the planning documents for the full design and phased
build order:

- [`docs/retinode-project-plan-revised.md`](docs/retinode-project-plan-revised.md) — current plan
- [`docs/retinode-project-plan.md`](docs/retinode-project-plan.md) — earlier draft

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```
