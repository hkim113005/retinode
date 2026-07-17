# Phase 7 — The polished application (FastAPI + React)

**Goal.** Re-skin the working tool as a clean **FastAPI backend + React frontend** in
the instrument-panel visual language, exposing the *whole* engine — not just the P2
single-config preview but **Compare, Study/Pareto, Validation, and Candidates**,
including the 3D geometry from Phase 6 (bodies, CAD, tilt) and the study/surrogate
engine from Phase 5. A real 2D charting layer carries the load; a secondary
react-three-fiber 3D scene shows the array and field; every plot exports at figure
quality (SVG/PDF vector, high-DPI PNG).

The engine and specs are **unchanged**, and the view data contracts (§16 of the
master plan — today `app/views.py`) are the fixed seam. That is what makes this a
**re-skin of a working tool, not a rewrite of the science** (master plan §17). A CI
lint boundary already exists in intent: `engine/` may not import from `api/` or
`app/`.

**Done when** a labmate can, in the browser: (1) lay out or **import** an array
(flat, 3D primitive, or CAD; posed and tilted), see the **analytical field preview
update live** as they edit; (2) hit **Run accurately**, watch an FEM/NEURON job
stream progress, and see results re-render **badged FEM** with a note where FEM
diverged from analytical; (3) open **Study**, sweep geometry/config to a
**selectivity-versus-cost Pareto frontier**, and click any point to inspect it; (4)
check **Validation** (the reproductions still pass, solvers agree); (5) open
**Candidates**, read a ranked safety-filtered shortlist with rationale and tier, and
**export** it plus figure-quality plots — every result **reproducible from its
provenance record**.

**Why it matters.** The science is in hand (Phases 0–6); Phase 8 turns it into a
defensible design finding. Phase 7 is what makes the tool **legible and handable** —
"half the point is putting these in front of the lab" (master plan §16). It adds no
new physics: it raises *legibility and reach*, not fidelity. It is explicitly gated
— **"if warranted"** — because the existing Dash app is already genuinely usable on
the analytical tier; P7 earns its cost only if the tool proves worth productizing.

---

## What exists today (read first)

Phase 2 shipped a **Dash/Plotly** single-page app (`app/ui.py`, `app/scene.py`,
`app/views.py`): a control rail → a live **analytical** field heatmap + a
**scorecard** (operating window) + a runs strip + a **Validation** panel. It is
monopolar/bipolar, single-config, analytical-only. It does **not** expose the study
sweep (P5), the Pareto frontier, 3D geometry (P6), or figure export.

The clean split it already has is the asset P7 builds on:

- **`app/views.py` is the view data contract** — pure functions (`field_grid`,
  `scorecard_data`, `load_validation_report`) that compute straight from the engine
  and return plain data, plus a thin figure layer. P7 lifts the *data* functions
  into typed API responses and rebuilds the *figure* layer in React.
- **`app/scene.py`** builds spec objects from UI controls — the geometry-editing
  logic P7's forms reuse.

---

## Locked decisions

- **D1 — FastAPI backend (`api/`) + React client (`app/`).** The API imports the
  engine and exposes it; the React client talks only to the API. **`engine/` never
  imports `api/` or `app/`** — one CI lint rule (already called for in the master
  plan) guards the boundary that keeps this a re-skin. React is Vite + **TypeScript**.
- **D2 — The view data contract is the fixed seam.** Port `app/views.py`'s data
  functions to **Pydantic response models**; generate **TypeScript types from the
  OpenAPI schema** so the contract is enforced end to end. New screens (Study,
  Candidates) extend the contract with the same discipline: pure engine data in,
  typed payload out, thin React rendering.
- **D3 — Two-tier responsiveness.** The **analytical** field + scorecard are
  synchronous and fast (<~100 ms, no NEURON) — the live-preview path. **FEM,
  NEURON, and sweeps are asynchronous jobs** over the Phase-5 runner and the project
  store, streaming progress and **cached by `result_key`**. The UI badges every
  result with its tier (analytical / FEM) and never blocks on a long solve.
- **D4 — Job model, not blocking calls.** Submit → queue → poll (or WebSocket) →
  cached result. Jobs are **resumable** (Phase-5 `runner.py`) and content-addressed,
  so a re-submitted config is served from disk. Progress is the P5 progress callback
  surfaced over the wire.
- **D5 — The two-env reality is handled, not hidden.** The API server runs under
  **uv** (analytical + cable). **FEM needs the conda env**, so an FEM job is
  dispatched to the `retinode-fem` interpreter (subprocess/worker) or served from
  cache; the live app is *analytical + cached FEM*, and a fresh FEM solve is a
  background job with a visible "computing accurately…" state. This is stated in the
  UI, not papered over.
- **D6 — 2D primary, 3D secondary.** The field heatmap + isopotential contours, the
  activation-vs-amplitude curve, and the Pareto/threshold plots do the work
  (legible, fast, vector-exportable). A **react-three-fiber** scene shows the array
  (bodies, tilt, CAD) + tissue + cell population + overlap flags — available but
  secondary, "since 3D often impresses more than it informs" (master plan §16).
- **D7 — One color vocabulary, one visual language.** Cool = potential, warm =
  activation, alert = safety limit — reused from the instrument-panel identity so the
  whole tool reads as one thing. The existing Dash palette (`#1f2933` ink, `#0a84ff`
  accent) is the starting point.
- **D8 — Figure-quality export is a first-class feature.** Every plot exports as
  **SVG/PDF (vector)** and **high-DPI PNG (raster)** — because the deliverable is
  figures in front of the lab.
- **D9 — No regression during the cutover.** The Dash app keeps working until the
  React app reaches parity; both share the engine and the view contract, so they
  can coexist. Retiring Dash is the *last* step, only once parity is proven.

---

## Module layout

```
api/                     # FastAPI; imports engine, NEVER the reverse
  __init__.py
  main.py                # app factory, CORS, static-serve the built React bundle
  models.py              # Pydantic request/response models = the typed view contract
  routes/
    compare.py           # analytical field grid + scorecard (sync); evaluate (job)
    study.py             # geometry/config sweep -> Pareto (job); cost estimate
    validation.py        # the committed reproductions report
    candidates.py        # ranked, safety-filtered shortlist + export
  jobs.py                # async job model over engine.study.runner + the project store
  fem_worker.py          # dispatch an FEM job to the conda (retinode-fem) interpreter

app/                     # was Dash (Phase 2); becomes the React client (Phase 7)
  web/                   # Vite + TypeScript + react-three-fiber + charting
    src/
      api/               # generated TS types from the OpenAPI schema + a typed client
      screens/           # Compare, Study, Validation, Candidates
      scene3d/           # react-three-fiber array/tissue/cells/overlap
      charts/            # the 2D charting layer + figure-quality export
      ui/                # instrument-panel components, one color vocabulary
  ui.py, scene.py, views.py   # the Dash app + view contract — kept until React parity
```

`engine/` is untouched. `app/views.py`'s data functions are the reference the
Pydantic models mirror.

---

## Ordered steps

- **P7 S1 — API skeleton + the typed contract + the boundary lint.** Stand up
  FastAPI over the engine. Port `field_grid` / `scorecard_data` /
  `load_validation_report` into **Pydantic response models** and a synchronous
  **Compare** endpoint (analytical field grid + scorecard for a posed array + config
  + patch). Add the CI rule **`engine/` must not import `api/` or `app/`** (a grep or
  import-linter check). *Done:* `GET/POST /compare` returns the same numbers the Dash
  view does, typed; the boundary lint is green.

- **P7 S2 — React scaffold + the Compare screen (parity with Dash).** Vite + TS
  client; **generate TS types from the OpenAPI schema**; build the control rail →
  **live analytical field + scorecard**, reusing `scene.py`'s geometry-from-controls
  logic on the server. Instrument-panel styling, one color vocabulary. *Done:* the
  React Compare screen reproduces the Dash Compare, live, on the analytical tier.

- **P7 S3 — The async job model (FEM/NEURON, streamed).** A job layer over
  `engine.study.runner` (resumable) + the project store: submit an **evaluate**
  (real NEURON thresholds) or an **FEM field** as a background job, stream P5
  progress, cache by `result_key`, dispatch FEM to the conda interpreter (D5).
  Wire the **"Run accurately"** flow: results re-render **badged FEM** with a
  **divergence note** vs analytical. *Done:* a config runs to a real
  threshold/FEM result without blocking, and a re-submit is served from cache.

- **P7 S4 — Study & Pareto screen.** Build a sweep by choosing parameters + ranges
  (electrode size, pitch, return radius, steering weights — **and** 3D pillar
  diameter/pitch/height from P6). Show the **cost estimate**, launch, watch an
  incrementally-filling table and the **selectivity-versus-cost Pareto frontier**
  (P5 `geometry_sweep` + `pareto_selectivity_safety`). Click a point → inspect its
  field + scorecard. *Done:* a geometry sweep fills a frontier in the browser, each
  point inspectable.

- **P7 S5 — The 3D scene (react-three-fiber).** Render the posed array — flat faces,
  3D bodies, **tilt**, imported CAD — plus the tissue slab, the cell population, and
  **overlap flags** (a compartment inside a body). Reads the geometry spec + field;
  secondary to the 2D views (D6). *Done:* a planted 3D/tilted array and its overlap
  flags are visible and rotatable.

- **P7 S6 — Validation & Candidates screens.** Port the **reproductions panel** (the
  committed validation report + solver agreement). Build **Candidates** — the payoff
  screen: a ranked, **safety-filtered shortlist** with predicted selectivity,
  threshold, charge verdict, **accuracy tier**, trajectory sensitivity, and a
  one-line rationale, **exportable** as a report and a machine-readable list. *Done:*
  Validation shows 13/13 (or current), Candidates ranks and exports.

- **P7 S7 — The charting layer + figure-quality export.** A real 2D charting layer
  for the field heatmap + isopotential contours, the activation-vs-amplitude curve,
  the threshold plot, and the Pareto scatter (hover for values, click to inspect,
  **brush to select** on Pareto). **Export every plot** at figure quality — SVG/PDF
  vector, high-DPI PNG (D8). *Done:* each workhorse plot renders and exports vector +
  raster.

- **P7 S8 — Polish + parity cutover.** Keyboard- and mobile-respectful layout, empty
  and error states (including the evaluator's **refusal to compare mismatched
  off-target sets** surfaced as an actionable warning, not a silent bad chart), the
  full instrument-panel language, and docs. **Retire the Dash app only once React is
  at parity.** *Done:* the app is legible to a newcomer with the full screen set, and
  Dash is retired without loss.

---

## Testing strategy

- **`api` (fast, uv):** Pydantic model round-trips; endpoint smoke tests (Compare
  returns the same numbers as `app/views.py`); the **boundary lint** (`engine/`
  imports nothing from `api/`/`app/`) as a CI check; the job model with a fake
  runner (submit → progress → cached result), no NEURON.
- **`neuron` (uv):** one end-to-end job — submit an evaluate, get a real
  threshold-backed Compare result through the API.
- **`fem` (conda):** the FEM-worker dispatch path returns a field result for a 3D
  array (reuses the Phase-6 mesh; the API just orchestrates).
- **Frontend:** component tests for each screen against **mocked API responses**
  (the generated types make the mocks honest); a **Playwright** happy-path e2e
  (edit → live preview → Run accurately → inspect) against a running API on the
  analytical tier; optional visual-regression on the instrument-panel components.
- **Contract:** the OpenAPI schema is the single source; a CI step regenerates the TS
  types and fails if they drift from what the client compiled against.

---

## Validation & honesty

- **This is polish, not science.** P7 changes no physics and no numbers; it must
  render exactly what the engine computes, tier-badged. The biophysics caveats
  (mouse RGC morphology, trend-not-magnitude, FEM-only shaped/3D) are unchanged and
  stay visible in the UI, not buried.
- **The two-env latency is shown, not hidden.** Analytical is instant; FEM/NEURON
  are visibly asynchronous. The UI never implies a fresh FEM answer is free.
- **3D is secondary on purpose.** The scene is for intuition; the 2D plots and the
  numbers are the truth. Where FEM and analytical disagree, the UI says so.
- **The contract is the guardrail.** If a screen needs data the view contract does
  not expose, the fix is to extend the *contract* (engine → typed payload), never to
  reach around it — that discipline is what keeps the re-skin honest.

---

## What to cut under pressure, in order

1. **The 3D scene (S5)** — secondary by design; the 2D views carry the tool.
2. **Figure-quality vector export (S7)** — high-DPI PNG alone is serviceable
   short-term.
3. **Candidates export formats (S6)** — an on-screen ranked list before the
   machine-readable/report export.
4. **The React re-skin entirely** — if "if warranted" resolves to *not yet*, the
   Dash app already covers Compare + Validation on the analytical tier; ship P8's
   finding on Dash and revisit P7 later.

The irreducible core if P7 runs at all: **S1–S4** (API + Compare + jobs + Pareto) —
that is the full analyse-and-compare loop in a clean app.

---

## Compute & dependencies

- **Backend (uv):** `fastapi`, `uvicorn`, `pydantic`. The API server is light; the
  work is in the engine and the (already-built) study runner + store.
- **FEM dispatch:** the API shells FEM jobs to the `retinode-fem` conda interpreter
  (D5) — no new dependency, just process orchestration.
- **Frontend (Node/Vite):** `react`, `typescript`, `vite`, `@react-three/fiber` +
  `three`, a charting layer (e.g. `visx`/`d3` for vector-export control, or Plotly
  for speed — decided at S7), and an OpenAPI→TS type generator. The frontend
  toolchain is isolated under `app/web/` and does not touch the Python envs.
