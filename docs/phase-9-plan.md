# Phase 9 plan: packaging, docs, and release

## Goal

Make Retinode installable, reproducible, and legible to a stranger. The engine and app
already work and are documented; P9 is the finishing pass that turns a working repo into
a *release-ready* one: a clean install, a one-command reproduction backed by
provenance, and the docs a newcomer needs.

## Decisions (locked)

- **The headline result is the FEM geometry-distinction demo.** No novel scientific
  *design finding* exists yet: `docs/phase-8-findings.md` honestly records the
  analytical tier's limits, which is not a finding. The reproducible headline is
  instead the capability the whole tool exists for. **Two flat disks (d10, d30) score
  byte-identically on the analytical tier and distinctly on FEM** (9.49 µA against
  10.20 µA). It reproduces the P8-findings numbers and fails if the engine drifts.
  Producing an actual novel design finding is future science, really the scientific
  half of P8, and is noted below.
- **The repo stays private.** P9's stated end-state is a public repo; that was put on
  hold. So P9 lands as **release-ready, not yet published**: everything is done so it
  *could* go public with one click, but visibility is not flipped. Publishing and a
  cold clone by a stranger are deferred (see below).

## Slices

### S1: LICENSE and packaging polish
- Add `LICENSE` (MIT, already declared in `pyproject.toml`).
- Polish `pyproject.toml`: `keywords`, trove `classifiers`, `[project.urls]`
  (Homepage, Repository, Docs), and a sharper `description`. Keep the engine core
  numpy- and scipy-only; everything heavy stays an opt-in extra.
- Verify `uv build` produces a wheel and an sdist, and that the engine imports from a
  clean install.

### S2: one-command headline reproduction
- `examples/reproduce_headline.py`: score a d10 and a d30 flat disk. Show they are
  **identical on `AnalyticalBackend`** (the point source is diameter-blind) and
  **distinct on `FenicsxBackend`** (FEM sees the extent). Assert the FEM thresholds
  match the recorded provenance values within tolerance, so a regression fails the repro.
- It needs the conda `retinode-fem` env for FEM. Document the exact command. A fast
  analytical-tier check runs anywhere; the FEM headline is the conda command.
- Verify live in the conda env.

### S3: reproducibility docs and CONTRIBUTING
- A **"Reproduce the headline result"** section (README and `docs/user-guide.md`) with
  the one command and its expected output.
- A short **reproducibility guarantees** note: what is pinned, the tolerance, and how
  the provenance key (`result_key`, `offtarget_hash`) identifies a result.
- `CONTRIBUTING.md`: dev setup, the test markers (`neuron`, `slow`, `fem`), and the
  load-bearing boundary rule (`engine/` imports neither `api/` nor `app/`).

### S4: release-readiness verification, plan, and tracker
- Cold-install the built wheel into a fresh venv and import the engine, which proves
  the sdist and wheel are self-contained for the core.
- Run the one-command repro end to end.
- Write this plan; update the tracker's P9 to read **release-ready, not published**.

## Deferred (explicitly)

- **Publishing publicly and a cold clone by a stranger.** The repo stays private by
  decision. When it goes public: flip visibility, then have someone clone cold and run
  the repro.
- **A novel design finding**, the scientific P8 deliverable: which geometry dominates
  the frontier, and why. The tooling is built; producing and defending the finding is
  future work. The headline repro is a *capability* demo, honestly labelled as such.
- **Publishing to PyPI.** The package is build-ready; actually uploading it is out of
  scope while the repo is private.

## Verification

- `uv build` succeeds, and a fresh-venv install imports `engine`.
- `uv run ruff check .` and `uv run pytest -m "not slow and not neuron and not fem"`
  are green.
- The conda one-command repro prints the d10≠d30 FEM distinction and its provenance
  check passes.
- Commit each slice; run the papers and settings guard before every commit; attribution
  stays off; never stage `papers/` or `.claude/settings.local.json`.
