# Phase 9 — Packaging, docs, and release

## Goal

Make Retinode installable, reproducible, and legible to a stranger. The engine and app
already work and are documented; P9 is the finishing pass that turns a working repo into
a *release-ready* one — a clean install, a one-command reproduction backed by
provenance, and the docs a newcomer needs.

## Decisions (locked)

- **The headline result is the FEM geometry-distinction demo.** No novel scientific
  *design finding* exists yet — `docs/phase-8-findings.md` honestly records the
  analytical tier's limits, not a finding. The reproducible headline is instead the
  capability the whole tool exists for: **two flat disks (d10, d30) score
  byte-identically on the analytical tier and distinctly on FEM** (9.49 µA vs 10.20 µA).
  It reproduces the P8-findings numbers and fails if the engine drifts. Producing an
  actual novel design finding is future science (really P8), noted below.
- **The repo stays private.** P9's stated end-state is a public repo; that was put on
  hold. So P9 lands as **release-ready, not yet published** — everything is done so it
  *could* go public with one click, but visibility is not flipped. "Publish + cold clone
  by a stranger" is deferred (see below).

## Slices

### S1 — LICENSE + packaging polish
- Add `LICENSE` (MIT — already declared in `pyproject.toml`).
- Polish `pyproject.toml`: `keywords`, trove `classifiers`, `[project.urls]`
  (Homepage/Repository/Docs), sharpen `description`. Keep the engine core numpy/scipy-
  only; everything heavy stays an opt-in extra.
- Verify `uv build` produces a wheel + sdist and the engine imports from a clean install.

### S2 — One-command headline reproduction
- `examples/reproduce_headline.py`: score a d10 and a d30 flat disk. Show they are
  **identical on `AnalyticalBackend`** (the point source is diameter-blind) and
  **distinct on `FenicsxBackend`** (FEM sees the extent). Assert the FEM thresholds
  match the recorded provenance values within tolerance, so a regression fails the repro.
- It needs the conda `retinode-fem` env (FEM). Document the exact command. A fast
  analytical-tier check runs anywhere; the FEM headline is the conda command.
- Verify live in the conda env.

### S3 — Reproducibility docs + CONTRIBUTING
- A **"Reproduce the headline result"** section (README + `docs/user-guide.md`) with the
  one command and expected output.
- A short **reproducibility guarantees** note: what's pinned, the tolerance, and how the
  provenance key (`result_key` / `offtarget_hash`) identifies a result.
- `CONTRIBUTING.md`: dev setup, the test markers (`neuron` / `slow` / `fem`), and the
  load-bearing boundary rule (`engine/` imports neither `api/` nor `app/`).

### S4 — Release-readiness verification + plan/tracker
- Cold-install the built wheel into a fresh venv; import the engine (proves the sdist/
  wheel is self-contained for the core).
- Run the one-command repro end to end.
- Write this plan; update the tracker's P9 to reflect **release-ready, not published**.

## Deferred (explicitly)

- **Publish public + cold clone by a stranger** — the repo stays private by decision.
  When it goes public: flip visibility, then have someone clone cold and run the repro.
- **A novel design finding** — the scientific P8 deliverable (which geometry dominates
  the frontier and why). The tooling is built; producing and defending the finding is
  future work. The headline repro is a *capability* demo, honestly labelled as such.
- **Publishing to PyPI** — the package is build-ready; actually uploading is out of
  scope while the repo is private.

## Verification

- `uv build` succeeds; a fresh-venv install imports `engine`.
- `uv run ruff check .` + `uv run pytest -m "not slow and not neuron and not fem"` green.
- The conda one-command repro prints the d10≠d30 FEM distinction and its provenance
  check passes.
- Commit each slice; run the papers/settings guard before every commit; attribution
  stays off; never stage `papers/` or `.claude/settings.local.json`.
