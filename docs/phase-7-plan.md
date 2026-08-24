# Phase 7: the polished application (FastAPI + React)

**Goal.** Re-skin the working tool as a clean **FastAPI backend plus React
frontend** in the instrument-panel visual language, exposing the *whole* engine: not
just the P2 single-config preview but **Compare, Study/Pareto, Validation, and
Candidates**, including the 3D geometry from Phase 6 (bodies, CAD, tilt) and the
study and surrogate engine from Phase 5. A real 2D charting layer carries the load;
a secondary react-three-fiber 3D scene shows the array and field; every plot exports
at figure quality (vector SVG, high-DPI PNG).

The **UX/UI craft bar** for this phase is its own document,
[phase-7-design.md](phase-7-design.md), with an interactive mockup of the Results
screen at [docs/mockups/results-screen.html](mockups/results-screen.html). The plan
below is *what* to build; the design spec is *how good it must feel* (an instrument,
not a dashboard), and every step here is held to it.

The engine and specs are **unchanged**, and the view data contracts (§16 of the
master plan, today `app/views.py`) are the fixed seam. That is what makes this a
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
**export** it plus figure-quality plots, with every result **reproducible from its
provenance record**.

**Why it matters.** The science is in hand (Phases 0–6); Phase 8 turns it into a
defensible design finding. Phase 7 is what makes the tool **legible and handable**,
because "half the point is putting these in front of the lab" (master plan §16). It
adds no new physics: it raises *legibility and reach*, not fidelity. It is
explicitly gated on **"if warranted"**, because the existing Dash app is already
genuinely usable on the analytical tier, so P7 earns its cost only if the tool
proves worth productizing.

---

## What exists today (read first)

Phase 2 shipped a **Dash/Plotly** single-page app (`app/ui.py`, `app/scene.py`,
`app/views.py`): a control rail → a live **analytical** field heatmap + a
**scorecard** (operating window) + a runs strip + a **Validation** panel. It is
monopolar/bipolar, single-config, analytical-only. It does **not** expose the study
sweep (P5), the Pareto frontier, 3D geometry (P6), or figure export.

The clean split it already has is the asset P7 builds on:

- **`app/views.py` is the view data contract:** pure functions (`field_grid`,
  `scorecard_data`, `load_validation_report`) that compute straight from the engine
  and return plain data, plus a thin figure layer. P7 lifts the *data* functions
  into typed API responses and rebuilds the *figure* layer in React.
- **`app/scene.py`** builds spec objects from UI controls. That is the
  geometry-editing logic P7's forms reuse.

---

## Locked decisions

- **D1: FastAPI backend (`api/`) plus React client (`app/`).** The API imports the
  engine and exposes it; the React client talks only to the API. **`engine/` never
  imports `api/` or `app/`**, and one CI lint rule (already called for in the master
  plan) guards the boundary that keeps this a re-skin. React is Vite plus
  **TypeScript**.
- **D2: The view data contract is the fixed seam.** Port `app/views.py`'s data
  functions to **Pydantic response models**, and generate **TypeScript types from
  the OpenAPI schema** so the contract is enforced end to end. New screens (Study,
  Candidates) extend the contract with the same discipline: pure engine data in,
  typed payload out, thin React rendering.
- **D3: Two-tier responsiveness.** The **analytical** field and scorecard are
  synchronous and fast (under ~100 ms, no NEURON), which is the live-preview path.
  **FEM, NEURON, and sweeps are asynchronous jobs** over the Phase-5 runner and the
  project store, streaming progress and **cached by `result_key`**. The UI badges
  every result with its tier (analytical or FEM) and never blocks on a long solve.
- **D4: Job model, not blocking calls.** Submit → queue → poll (or WebSocket) →
  cached result. Jobs are **resumable** (Phase-5 `runner.py`) and content-addressed,
  so a re-submitted config is served from disk. Progress is the P5 progress callback
  surfaced over the wire.
- **D5: The two-env reality is handled, not hidden.** The API server runs under
  **uv** (analytical plus cable). **FEM needs the conda env**, so an FEM job is
  dispatched to the `retinode-fem` interpreter (a subprocess worker) or served from
  cache. The live app is *analytical plus cached FEM*, and a fresh FEM solve is a
  background job with a visible "computing accurately…" state. This is stated in the
  UI, not papered over.
- **D6: 2D primary, 3D secondary.** The field heatmap with isopotential contours,
  the activation-vs-amplitude curve, and the Pareto and threshold plots do the work,
  because they are legible, fast, and vector-exportable. A **react-three-fiber**
  scene shows the array (bodies, tilt, CAD), the tissue, the cell population, and
  overlap flags. It is available but secondary, "since 3D often impresses more than
  it informs" (master plan §16).
- **D7: One color vocabulary, one visual language.** Cool means potential, warm
  means activation, alert means safety limit, all reused from the instrument-panel
  identity so the whole tool reads as one thing. The existing Dash palette
  (`#1f2933` ink, `#0a84ff` accent) is the starting point.
- **D8: Figure-quality export is a first-class feature.** Every plot exports as
  **vector (SVG)** and **high-DPI raster (PNG)**, because the deliverable is figures
  in front of the lab. *(Amended in P8: this said "SVG/PDF". PDF was assessed and
  deliberately dropped rather than left as an unmet promise; the reasoning is under
  S7a's deferral note below. `docs/phase-7-design.md`, which is the acceptance bar
  for this plan, always said "vector/raster" and is met.)*
- **D9: No regression during the cutover.** The Dash app keeps working until the
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
  ui.py, scene.py, views.py   # the Dash app + view contract; kept until React parity
```

`engine/` is untouched. `app/views.py`'s data functions are the reference the
Pydantic models mirror.

---

## Ordered steps

- **P7 S1: API skeleton, the typed contract, and the boundary lint. Done.** FastAPI
  over the engine (`api/`: `models.py` for the Pydantic contract, `service.py` for
  engine→payload, `routes/compare.py`, and `main.py` for the app factory, CORS, and
  `/health`). `POST /compare` builds the scene from the controls
  (`app.scene.build_scene`), returns the analytical **field grid synchronously and
  NEURON-free**, and computes the operating-window **scorecard only when asked**
  (`include_scorecard`) through an **injectable threshold provider**: a fast fake in
  tests, the real population solve in production, which S3 moves to a job. A
  **parity test** locks the endpoint's field and scorecard to the exact numbers
  `app.views` produces, and the **boundary lint** (`engine/` imports nothing from
  `api`/`app`) is a test in CI. The OpenAPI schema exposes `CompareResponse` for
  S2's generated TS types. `--extra api` (fastapi, httpx) was added to the fast and
  neuron CI jobs. 331 fast tests pass, ruff clean.

- **P7 S2: React scaffold and the Compare screen (parity with Dash). Done.** A
  Vite + React + TypeScript client under `app/web/`, in the instrument-panel design
  language (`docs/phase-7-design.md`), talking only to the typed `/compare` contract.
  TS types are **generated from the OpenAPI schema**: `openapi-typescript` reads a
  committed `openapi.json` snapshot, kept honest by a Python snapshot test and a CI
  types-in-sync check. The **Compare** screen has the left pipeline rail, a control
  rail (layout and sliders), a **live analytical field canvas** (debounced
  `POST /compare`, a diverging Ve heatmap with electrode and cell overlays), and an
  **on-demand scorecard** in separate state, so a field refetch never clobbers it.
  The field-view contract gained electrode and soma overlays (master plan §16).
  Vitest component tests run against mocked responses, and a new **`web` CI job**
  runs types-in-sync, typecheck, test, and build. Verified live end-to-end in the
  browser: the field renders and updates on control edits (monopolar → bipolar
  dipole). 7 web tests, 333 fast.

- **P7 S3: The async job model (NEURON scorecard). Done, with FEM dispatch as a
  follow-up.** A dependency-free in-process job model (`api/jobs.py`: a thread pool,
  a lock, and a result cache). `submit(key, task)` runs a task on a background
  thread, tracks progress, and **caches by key**, so a re-submit is served instantly.
  The scorecard now runs through it: `POST /score` submits a job that runs `evaluate`
  (the real NEURON population solve in production, an injectable fake in tests), and
  `GET /jobs/{id}` polls progress. The React Compare screen **submits then polls**,
  showing a progress bar while the job runs and a **cached** badge when the result is
  reused; the scorecard is separate state, so a field refetch never clobbers it.
  Verified live in the browser (submit → progress → operating window, with a control
  change invalidating the cache so the safety ceiling recomputes) and over HTTP
  (running → done → cached). Tests: the registry (run, cache, error), the endpoints
  with a fast fake, a `neuron`-marked real-threshold job, and web tests for the poll
  and cache paths. *Done:* a config runs to a real threshold result without blocking,
  and a re-submit is served from cache.

- **P7 S3b: FEM "Run accurately" dispatch (D5). Done.** The exact field crosses the
  two-env boundary. `api/fem_job.py` is the conda-side solver: it reads a scene on
  stdin, meshes tissue-minus-electrode, solves the DOLFINx field, and writes the grid
  to a temp file so gmsh and PETSc stdout noise cannot corrupt it. `api/fem_worker.py`
  invokes it as a subprocess in the `retinode-fem` interpreter
  (`$RETINODE_FEM_PYTHON`), then computes the field's **divergence from the
  analytical preview**. `api/__init__` is now lazy so `api.fem_job` imports in the FEM
  env, where FastAPI is absent. `POST /field/accurate` submits the solve as a job on
  the same registry, and the React **"Run accurately (FEM)"** flow polls it and
  re-renders the field **badged FEM** (tier draft→inked, the rail Accuracy badge
  flips) with the divergence note. Tests: `fem_worker` with a mocked subprocess plus
  the endpoint via the job (fast job); `tests/field/test_fem_dispatch.py` runs the
  real conda-side solver (`fem` job). Verified live end-to-end: uv React → uv API →
  subprocess → conda DOLFINx → re-render, a 21% divergence on a 10 µm disk in ~18 s.
  **S3 complete.**

- **P7 S4: Study and Pareto screen. Done (core).** `POST /study` submits a geometry
  sweep (P5 `geometry_grid` × `monopolar_center`) as a job on the shared registry,
  streaming per-geometry progress. Each activated geometry becomes a point
  (`cost_uA` = target threshold, `selectivity_uA` = usable window, plus `safe`), and
  the endpoint marks the **selectivity-versus-cost frontier**: a safe point beaten on
  neither axis. That is the master-plan §15 frontier, distinct from the engine's
  selectivity-vs-safety `pareto`. The React **Study** screen has a sweep builder
  (diameter × pitch chips) with a live **cost estimate**, then **Run study** → poll →
  a **Pareto plot** (`ParetoPlot` canvas: the frontier as a lit curve, dominated
  points receding, unsafe ones hollow red, click a point to inspect its geometry and
  metrics). The rail now **navigates** (Compare ↔ Study). Tests: the sweep endpoint
  with a geometry-varying fake provider plus a `neuron`-marked real sweep, and web
  tests (cost estimate, run→frontier, nav). Verified live: 16 geometries produced a
  3-point frontier with click-to-inspect (d16·p40, a 9.6–10.1 µA window).
  **Trimmed to follow-ups:** brush-select → Candidates, ghost-field-on-hover, small
  multiples, incremental fill, and the 3D pillar sweep.

  > **Corrected in P8 S4.** That live run used a **fake thresholds provider** whose
  > invented cost depended on diameter. The real analytical tier is a point source
  > and cannot see diameter or pitch, so the frontier it produces is flat by
  > construction. Study now dispatches to FEM. See
  > [phase-8-findings.md](phase-8-findings.md).

- **P7 S5: The 3D loupe (react-three-fiber). Done.** A `Loupe3D` component renders
  the scene's geometry in 3D: the translucent **tissue slab**, the **array-plane
  grid**, the **electrode disks** on the plane, and the **cell population** at depth
  (target amber, off-target blue). It orbits (drei `OrbitControls`), exaggerates the
  depth axis ~5× so the thin retinal layer reads, and fits the view to the geometry.
  It docks as an auto-spinning **corner inset** on the Compare field canvas and
  **expands** to a fully orbitable overlay, inking up when the tier is FEM.
  three.js is **lazy-loaded**, code-split into its own ~225 KB-gzip chunk, off the
  51 KB main bundle and out of the sync test path; jsdom's missing WebGL is handled
  by stubbing the r3f `Canvas` globally in the test setup. Secondary to the 2D field
  (D6). Verified live: the tissue, plane, electrode, and cell scene renders and
  orbits.

  > **Correction (P8).** This entry originally claimed that "3D bodies / tilt / CAD /
  > overlap flags render when the geometry carries them", with the flat Compare scene
  > showing flat disks. **The first half was false.** The view contract is flat:
  > `ElectrodeMarker` is `{x_um, y_um, radius_um}`, with no z, no rotation, and no
  > body. No geometry can carry them, and `Loupe3D` contains no body-rendering
  > code that such data could trigger. It was not a dormant path waiting on a
  > payload; it did not exist. The loupe draws flat disks, full stop. Unstranding
  > Phase 6's 3D work needs a contract that *carries* a body **and** a surface that
  > *authors* one. See the P8 assessment below.

- **P7 S6: Validation and Candidates screens. Done.** `GET /validation` serves the
  **committed** report (`app/validation_report.json`). The API renders it and never
  recomputes it, and a test asserts the response is byte-equal to the file, so the
  screen cannot drift from what CI regenerates. **Validation** shows the pass count
  and one row per claim (source, criterion, measurement, and the honest note where a
  reproduction is partial or deferred). **Candidates** ranks the study's sweep:
  charge-unsafe designs are filtered out entirely, the rest are ordered by the
  selective window, each with a generated one-line rationale, the accuracy tier, and
  the frontier flag, and the top design headlines a recommendation. It exports as
  JSON and CSV. `App` lifts the study points so a sweep on Study carries to
  Candidates without a re-run. *Verified live:* Validation renders 13/13, and a
  16-geometry sweep produced 3 frontier points and 8 ranked charge-safe candidates.
  *(Deferred: trajectory sensitivity per candidate. **See the P8 correction: this is
  the axon-trajectory distribution (`engine/cable/trajectories.py`), not array
  placement.** The figure-quality report export lands with the charting layer in
  S7.)*

- **P7 S7: The charting layer and figure-quality export.** A real 2D charting layer
  for the field heatmap with isopotential contours, the activation-vs-amplitude
  curve, the threshold plot, and the Pareto scatter (hover for values, click to
  inspect, **brush to select** on Pareto). **Export every plot** at figure quality:
  vector SVG and high-DPI PNG (D8). *Done:* each workhorse plot renders and exports
  vector and raster. Split into three slices:

  - **S7a: the chart core. Done.** The seam is a `Scene`: a plot is a *pure
    function* from data to a flat list of resolved primitives, and two renderers
    consume it, canvas for the screen and SVG for export. The exported figure is
    therefore the same description the screen drew and **cannot drift** into a
    second, lookalike implementation of the plot. Colours resolve at build time,
    because a `var(--…)` means nothing inside a standalone `.svg`. Export offers
    **SVG** (vector and editable, convertible to PDF or EPS via Illustrator or
    Inkscape) and **3× PNG** (~300 dpi), defaulting to a fixed **PAPER** palette
    rather than the live theme, because a dark-mode figure is unusable in a
    manuscript. Both plots gained what a *chart* needs over a picture: numeric
    **axis ticks** on the Pareto, a round-numbered **scale bar** on the field.
    Making the plots pure also gave them their first real test coverage, since
    jsdom cannot exercise canvas drawing at all. *Verified live:* the field exports
    a 720×720 SVG (3722 marks, no CSS vars, white paper) and a 2160×2160 PNG, and
    the Pareto exports a 3.4 KB vector with real `<text>` axes.
    **PDF: assessed in P8 and deliberately dropped, not deferred.** The original
    note here said "PDF is one Inkscape step from the SVG, a format the SVG already
    reaches". That was **wrong on its facts**: SVG is *not* a journal submission
    format, because Nature, Science, IEEE, PLOS, and eLife want EPS, PDF, TIFF, or
    AI. The decision survives on better reasons:

    1. *It cannot be built honestly at this scope.* The Pareto draws `→` and `◤`
       (`chart/plots/pareto.ts`), which are outside PDF's base-14 glyph coverage.
       Drawing them faithfully means TrueType subsetting, roughly 1000 lines of
       font-format work. The shippable alternative substitutes glyphs, which would
       make PDF the **first renderer here that does not draw what the screen drew**,
       breaking the one invariant S7a exists to hold. A convenience click is not
       worth the architecture's central guarantee.
    2. *It buys nothing.* Nobody submits a single-panel tool export as a figure;
       panels get composited and lettered in Illustrator or Inkscape regardless, and
       the SVG→PDF conversion is absorbed into that step rather than added to it.
    3. *A dependency is worse:* +110–150 KB gzip on a 60 KB app and a sixth runtime
       dependency, and `pdf-lib`/`jspdf` are base-14 too, so it does not even solve
       (1).
    4. *No test oracle.* `chart.test.ts` asserts on the SVG string. A PDF's
       correctness cannot be asserted in jsdom, leaving a permanent unautomatable
       hole in an otherwise fully-covered layer.

    The remaining real gap is `\includegraphics`, which wants PDF. That is served by
    a one-time `inkscape --export-type=pdf`, or by the 3× PNG for talks. D8's wording
    was amended to match what is actually delivered rather than left as an unmet
    promise.
  - **S7b: labeled isopotential contours and a hover readout. Done.** Marching
    squares (`chart/contours.ts`) traces isopotentials at **round** mV levels and
    stitches the raw segments into whole rings, so each contour is one stroked
    object: smooth on screen, and one `<path>` per ring in the figure rather than
    hundreds of disjoint sticks. Saddle cells are resolved by the centre value, not a
    coin flip. Every ring is **labelled with its own mV value** at its topmost point,
    and since the levels stack outward the labels never collide. Hovering the field
    reads the bilinearly-sampled `Ve` under the cursor into a fixed corner chip,
    because a readout that chases the mouse is harder to read than one that stays
    put. *Verified live:* rings at −2/−4/−6 mV around a 10 µm disk; the probe reads
    −7.95 mV at the centre (matching the ±7.96 colour limit) and −4.32 mV at 31 µm,
    exactly where the −4 mV ring falls, so the two readings cross-check each other.
  - **S7c: Pareto hover tooltip and brush-to-select. Done.** Hovering a design reads
    its geometry, threshold, window, and charge verdict into a tooltip bound to the
    mark. This one *does* follow the cursor, because unlike the field probe it
    belongs to a specific point rather than to the plot. Dragging a box brushes a
    set: a press-release is still a click, and past 4 px it becomes a brush, so
    inspecting and selecting share one gesture without a mode. **Only charge-safe
    designs are brushable**, since an unsafe one is not a candidate for anything. The
    brush lifts through `App` to Candidates, which ranks the subset and **says that
    it did**: the note reads "brushed from the study", with one click back to the
    whole sweep, and every superlative renames its scope ("the widest window in *your
    brushed selection*") rather than quietly claiming to speak for the study.
    *Verified live:* brushing the cheap-and-selective corner of a 16-geometry sweep
    shortlisted 8 charge-safe designs, 2 of them on the frontier, and moved the
    recommendation from d12 to d16·40, correctly reflecting what was actually asked
    for. This closes the S4 deferral "brush→Candidates".

  *(Deferred from S7, resolved in P8: the activation-vs-amplitude and threshold plots
  were built in P8 S1, described in [phase-8-plan.md](phase-8-plan.md). Native PDF was
  assessed and deliberately dropped in P8 S2. The "SVG already reaches PDF" reasoning
  here was wrong, because SVG is not a journal format, so D8's wording was amended to
  promise vector (SVG) plus raster (PNG), which is what ships.)*

- **P7 S8: Polish and the parity cutover. Done.**

  - **The parity audit came back negative, and that was the point of doing it.**
    React was *ahead on average* (FEM tier, Study, Candidates, export, 3D), but
    ahead on average is not parity. There were four real losses, every one fixable in
    the client because the contract already carried the data. **Tissue conductivity
    had no control at all**, with `sigma_S_per_m` pinned to 1, leaving a whole
    physics dimension unreachable. The **selectivity ratio** was fetched and dropped.
    So was **`limiting`**, so a user could not tell whether a bystander or the charge
    limit closed the window, which is the entire design decision. And **run history
    with restore** was absent. On top of that, quietly narrowed slider ranges
    (diameter 40→30, pitch and neighbour 160→120 µm) put real configurations out of
    reach, and an unbounded window rendered as the literal string `"Infinity µA"`.
    All closed.
  - **⌘K command palette + keyboard reachability.** Screens register their own
    commands, so a screen's actions live beside the code that runs them and leave
    when it unmounts. Navigation, both background jobs, the tier toggle and reset are
    reachable without a mouse; `:focus-visible` rings cost pointer users nothing, and
    `prefers-reduced-motion` is honoured.
  - **Error boundaries.** React had been warning in the console: any render error
    unmounted the whole tree, so one bad payload meant a white screen with the reason
    only in devtools. The field, the 3D loupe (WebGL is not guaranteed) and each
    screen now fail alone and can be retried.
  - **The off-target refusal, honestly.** `require_same_offtarget` forbids comparing
    windows scored against different bystanders, and the history strip is exactly
    such a comparison. So `offtarget_hash` now rides the contract (D9: extend the
    contract, never reach around it) and the strip flags a run it cannot compare.
    **The guard is dormant:** `OffTargetSet` is the *policy* (soma radius, axon
    proximity), not the cells it selects, and no control varies the policy, so every
    run shares one. It is enforced anyway, so the day the policy becomes editable the
    strip is already honest. Both semantics are pinned by tests.
  - **Dash retired, at parity, without loss.** `app/ui.py`, `app/__main__.py`,
    `app/assets/`, `tests/app/test_ui.py` and `views.field_figure` are gone, with the
    `dash` and `plotly` extras and the `--extra app` CI steps. **Kept:**
    `app/scene.py` (the API imports it; it was never Dash-only),
    `app/validation_report.json` (served by `GET /validation`), and `views.py`'s data
    functions, which outlived the UI as the API's **independent oracle**.
    `tests/api/test_compare` asserts the endpoints agree with them by a separate
    route, so the API is not merely checked against a snapshot of itself.

  *Done:* the app is legible to a newcomer with the full screen set, and Dash is
  retired without loss.

---

## Testing strategy

- **`api` (fast, uv):** Pydantic model round-trips; endpoint smoke tests (Compare
  returns the same numbers as `app/views.py`); the **boundary lint** (`engine/`
  imports nothing from `api/`/`app/`) as a CI check; the job model with a fake
  runner (submit → progress → cached result), no NEURON.
- **`neuron` (uv):** one end-to-end job. Submit an evaluate, get a real
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
  reach around it. That discipline is what keeps the re-skin honest.

---

## What to cut under pressure, in order

1. **The 3D scene (S5):** secondary by design, and the 2D views carry the tool.
2. **Figure-quality vector export (S7):** high-DPI PNG alone is serviceable
   short-term.
3. **Candidates export formats (S6):** an on-screen ranked list comes before the
   machine-readable and report exports.
4. **The React re-skin entirely.** If "if warranted" resolves to *not yet*, the
   Dash app already covers Compare and Validation on the analytical tier, so ship
   P8's finding on Dash and revisit P7 later.

The irreducible core if P7 runs at all is **S1–S4** (API, Compare, jobs, Pareto),
which is the full analyse-and-compare loop in a clean app.

---

## Compute & dependencies

- **Backend (uv):** `fastapi`, `uvicorn`, `pydantic`. The API server is light; the
  work is in the engine and the (already-built) study runner + store.
- **FEM dispatch:** the API shells FEM jobs out to the `retinode-fem` conda
  interpreter (D5). No new dependency, just process orchestration.
- **Frontend (Node/Vite):** `react`, `typescript`, `vite`, `@react-three/fiber` and
  `three`, a charting layer (`visx` or `d3` for vector-export control, or Plotly for
  speed, decided at S7), and an OpenAPI→TS type generator. The frontend toolchain is
  isolated under `app/web/` and does not touch the Python envs.

  > **What S7 actually chose:** no charting library. The chart core is hand-rolled
  > (`chart/`), a pure `Scene` with a canvas renderer and an SVG renderer, which is
  > what buys the guarantee that the exported figure is the same description the
  > screen drew. Runtime dependencies stayed at five: `react`, `react-dom`, `three`,
  > `@react-three/fiber`, `@react-three/drei`.
