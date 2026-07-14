# Comprehensive Design and Implementation Plan
## An epiretinal electrode-geometry selectivity testbed (Retinode)

This is a planning document. It designs the whole program, engine and application and interface, and how the parts fit, and lays out a revised, phased build order. It does not implement anything. The aim is a tool that is accurate enough to be trusted, clean enough to be pleasant, and easy enough that someone who is not you (Michael, a labmate) can sit down and use it to find electrode configurations worth testing in tissue.

Three commitments shape every decision below:
1. **Accurate.** Reproduce known results before trusting novel ones; make every result carry its accuracy tier and its sensitivity; treat safety as a first-class output.
2. **Usable.** A fast design loop, sensible defaults, progressive disclosure, and trust made visible.
3. **Honest.** The tool screens and generates hypotheses. It proposes configurations for ex vivo or in vivo testing. It is not, from simulation alone, a ground-truth oracle, and it says so in its own interface.

---

# Part I. What the program is

## 1. Vision and scope

**One sentence.** Retinode lets a user specify a hypothetical epiretinal electrode geometry and current configuration, simulate how it activates a population of retinal ganglion cells and their axons of passage, score its selectivity and safety, compare it against alternatives, and export a ranked shortlist of configurations worth testing in tissue.

**In scope.** Epiretinal, direct RGC and axon activation. Physical electrode geometry (size, shape, pitch, placement) and current configuration (which electrodes source and return, with what weights, including current steering). A field engine with swappable backends across accuracy tiers. A selectivity-and-safety evaluator. A study engine for parameter sweeps. A clean application with geometry editing, field and activation visualization, comparison and Pareto views, a validation dashboard, and candidate export.

**Out of scope (for now, stated so it does not creep).** Subretinal or suprachoroidal stimulation (different physics). Percept prediction (that is pulse2percept's job; a bridge to it is a possible later add). Closed-loop hardware control. Patient-specific anatomy. Manufacturing/fabrication modeling beyond electrode geometry.

**Audience.** You first. Then lab members who want to screen a geometry idea without writing simulation code. The second audience is why the UI matters: the tool has to be legible to someone who understands retinas but not your codebase.

## 2. Users and core journeys

The design is anchored on a small set of journeys. Everything in the UI exists to serve one of these.

- **Design and preview.** Lay out an electrode array over a retinal patch, set a current configuration, and immediately see the field and a fast selectivity estimate. Iterate quickly.
- **Run accurately.** Promote a promising design from the fast analytical preview to an accurate FEM run, and see how the answer changes.
- **Compare.** Put several configurations side by side, on the same patch and metric, and see which wins and why.
- **Sweep and find the frontier.** Define a study that varies geometry or configuration parameters across ranges, run it, and read the selectivity-versus-cost Pareto frontier.
- **Trust.** Check, in the interface, which published results the tool currently reproduces and how backends agree, so the numbers are believable.
- **Hand off.** Export a ranked, safety-checked shortlist of candidate configurations, with rationale and accuracy caveats, ready to discuss with the lab and test in tissue.

---

# Part II. System architecture

## 3. The shape of the system

Four layers, with a strict rule: **the engine knows nothing about the application, and the spec objects are the single source of truth that ties everything together.**

```
                        ┌───────────────────────────────────────────┐
                        │            FRONTEND (the app)              │
                        │  geometry editor · field & activation viz  │
                        │  compare · Pareto · validation · candidates│
                        └───────────────▲───────────────────────────┘
                                        │  JSON (spec objects) over HTTP
                        ┌───────────────┴───────────────────────────┐
                        │              API LAYER (FastAPI)           │
                        │  CRUD on projects/specs · run jobs (async) │
                        │  progress streaming · results & viz data   │
                        └───────────────▲───────────────────────────┘
                                        │  Python calls (same spec objects)
   ┌────────────────────────────────────┴──────────────────────────────────────┐
   │                                ENGINE (pure library)                        │
   │                                                                             │
   │  domain model / spec  ──►  field engine  ──►  cable engine  ──►  evaluator  │
   │  (electrodes, config,      (backends:         (NEURON,          (selectivity,│
   │   patch, conductivity,      analytical/         multi-site        threshold,  │
   │   study)                    FEniCSx/NGSolve/    activation,       charge,     │
   │                             Sim4Life/COMSOL)    thresholds)       area)       │
   │                                                                             │
   │  efficiency & compute (transfer-matrix reuse · parametric FEM · surrogate ·  │
   │   parallel · cluster/cloud adapters)   ·   persistence & provenance (cache,  │
   │   project store, versions, seeds)   ·   validation & test harness            │
   └─────────────────────────────────────────────────────────────────────────────┘
```

The spec objects (electrode array, current configuration, conductivity model, retinal patch, study definition) are the lingua franca. The same object, in four roles: it is the API payload, the on-disk project format, the cache key when hashed, and the thing the UI forms edit. Reproducibility becomes "save the spec plus the software versions." This one decision keeps the layers from drifting.

## 4. Why this layering

The engine is a plain Python library with no web or UI dependencies, so it runs equally from a notebook, a script, the test suite, or the app. The API is a thin translation of engine calls into HTTP plus a job model for long runs. The frontend is a client that edits specs and renders returned data. Because the engine is UI-independent, the frontend can start as a quick Python dashboard and later become a polished web app without touching the science. That migration path is a feature, not an afterthought.

---

# Part III. Component design (engine)

## 5. Domain model and the spec

The spec is the set of serializable objects that describe a simulation completely: the electrode array (physical geometry), the current configuration (which electrodes source and return, weights, waveform), the conductivity model (homogeneous or layered, with values and any anisotropy), and the retinal patch (RGC positions, morphologies, axon trajectories, and which cell is the target). A study definition sits above these, naming the parameters to vary and their ranges.

Responsibilities of this layer: strict validation (an array with duplicate electrode ids, a configuration whose currents do not charge-balance, a patch with no target, are all rejected with a clear message), stable serialization to and from JSON, and content hashing so any spec maps to a cache key. The terminology distinction is enforced structurally: geometry objects carry no current, configuration objects carry no geometry, so the two cannot blur. This is the keystone; design and freeze its interfaces before building anything on top.

## 6. Field engine

One contract makes solvers interchangeable: given an array, a conductivity model, and a set of query points, return the extracellular potential each electrode produces at those points, per unit current, as a transfer matrix. Linearity means one unit-current solve per electrode suffices and any configuration is a weighted sum.

Backends behind that contract, by accuracy tier: analytical point/disk source (Tier 1, fast, prototyping and the live preview); FEniCSx as the primary open-source FEM and NGSolve as its cross-check (Tier 2, the geometry study); Sim4Life as a field-only cross-check with its own solver; COMSOL later as a thin adapter for the lab. Swappability rests on a neutral geometry spec (electrode primitives plus conductivity slabs) that each backend meshes its own way, with gmsh as the shared mesh for the open-source solvers, and on the transfer matrix as the universal handoff so a backend can even run remotely (Sim4Life in the cloud) and return a file the pipeline imports.

Design concerns this layer owns: caching transfer matrices by (array, conductivity, query-point) hash so a fixed array is never re-solved; the honest boundary that changing physical geometry requires a new solve while changing configuration does not; and mesh-independence checks so no FEM number is trusted before convergence.

## 7. Cable and population engine

NEURON-backed multi-compartment RGC models (Fohlmeister-Miller channels) placed in the patch, driven by the field through the extracellular mechanism, with a bisection threshold search per cell. This engine owns the property the lab cares about most: **multi-site activation**. A spike initiating at any compartment counts, which is exactly why multi-electrode currents combine nonlinearly, and why running the full cable model rather than a single-site linear proxy is what keeps multi-electrode predictions honest. An optional, clearly-labeled subthreshold lead-field shortcut (reciprocity) may accelerate screening, but the full threshold search stays the ground truth.

Design concerns: mapping the field engine's query points back to per-cell compartments (the patch provides the index), sensible spike criteria and windows, and averaging over a distribution of axon trajectories rather than one, because thresholds are sensitive to the ascending axon path.

## 8. Evaluator

One fixed scorer, called identically for every configuration so comparisons are apples to apples. It produces the selective operating window (the current gap between the lowest off-target threshold and the target's, positive when a range fires only the target), the target and off-target thresholds, charge density per active electrode against a safety limit, and activated area. The off-target set is an explicit modeling choice (which neighboring somas and which bundle axons count) that the evaluator records with every result, because it shapes the numbers and Michael will have opinions about it. Safety is not a footnote here: a configuration that exceeds charge-density limits is flagged and excluded from any candidate shortlist, because the whole point is proposing things for real tissue.

## 9. Efficiency and compute

Two speeds, matching the two kinds of sweep. Configuration sweeps on a fixed array reuse one transfer matrix and are cheap, so they can run live. Physical-geometry sweeps recompute the field per geometry and are expensive, so they run as batched, parametric FEM jobs, coarse-to-fine, optionally with a surrogate model that emulates the selectivity score as a function of geometry parameters once enough points are sampled.

A thin job model wraps every long run (FEM solves, NEURON threshold searches, sweeps) as an async task with progress callbacks, a job store, and resumability, so nothing blocks and nothing is lost on a crash. Execution adapters cover local (a process pool), cluster (submit to Slurm on FarmShare or Sherlock through a sponsoring lab), and cloud (Sim4Life). The API exposes job status and streams progress to the UI. Cost estimation lives here too: before a study runs, estimate field-solves times per-solve time from a quick benchmark and surface it, so no one accidentally launches a three-day job.

## 10. Persistence and provenance

A project is a saved workspace: its specs, study definitions, cached transfer matrices (HDF5 or npz), results (a columnar store like parquet plus JSON), and a provenance log. Every run records the full spec, the software versions (NEURON, the FEM backend, the app), the git commit, the random seeds, and timestamps, so any figure can be regenerated and any result traced to exactly what produced it. The result cache is keyed by content hashes across geometry, configuration, conductivity, patch, backend, and parameters, so re-runs and overlapping sweeps reuse work automatically. Reproducibility is therefore not a feature bolted on at the end; it falls out of the spec-as-source-of-truth plus disciplined hashing.

## 11. Validation and test harness

Correctness is the product, so testing is part of the architecture, not a chore. Unit tests per component; property tests that assert the physics (linearity: the field of a sum of currents equals the sum of the fields); cross-backend agreement tests that fail if two solvers disagree beyond tolerance on a shared problem; and regression tests that reproduce Fan 2019 (local-return selectivity gain), Vilkhu 2021 (bi-electrode axon avoidance), and Vilkhu 2025 (multi-electrode nonlinearity) within tolerance and break the build if a change silently degrades them. These same checks feed the validation dashboard in the UI, so the tool's trustworthiness is both enforced in CI and visible to the user.

---

# Part IV. UI/UX design

The interface has to do something unusual: make an accurate, compute-heavy scientific tool feel light. The guiding ideas below all serve that.

## 12. UX principles

- **Two-speed by design.** Editing the geometry or configuration updates a fast analytical **preview** instantly, so the design loop never stalls. Accurate FEM is an explicit **Run accurately** action that queues an async job. The UI never pretends FEM is instant, and it never blocks on it.
- **Trust made visible.** Every result carries a small **tier badge** (analytical, FEM, Sim4Life-checked) and, where relevant, a sensitivity note. A validation panel shows which published results currently reproduce and how backends agree. The user should be able to see why to believe a number.
- **Safety inline.** Charge density against the electrode limit is shown wherever a configuration is, with anything unsafe flagged in place and kept out of candidate lists.
- **Progressive disclosure.** Strong defaults and templates up front (a standard array, a standard patch, a monopolar configuration), with advanced parameters (conductivity layers, mesh resolution, off-target definitions, trajectory distributions) tucked into expandable panels.
- **One vocabulary.** The precise terminology holds everywhere: geometry means the physical array, configuration means current delivery. Colors mean one thing throughout (a cool field color for potential, a warm signal color for activation, a distinct alert color for safety limits), reusing the instrument-panel identity from the tracker so the whole project feels like one thing.
- **Reproducibility as UX.** Any view can be saved, shared, and reopened to exactly its state, because it is just a spec plus a result reference.
- **Quality floor.** Responsive down to a laptop, visible keyboard focus, reduced motion respected, honest empty and error states that say what to do next.

## 13. Visual language

Instrument-panel, drawn from the subject's own world: the multi-electrode array, spike traces, isopotential contours. Graphite ink on a cool light ground, one cool accent for interaction and one warm accent reserved for activation and completion, hairline structure, a technical-but-humane type pairing (a grotesque display, a clean sans body, a mono for data and labels). Restraint everywhere except one signature moment: the live field-and-activation canvas, where the electrode array and the potential field and the firing cells are the hero. Everything else stays quiet so that canvas carries the page.

## 14. Information architecture

A single-project workspace with a persistent left rail of the stages and a main stage that changes with the step. The rail is the pipeline itself, which doubles as a progress indicator:

```
┌──────────────┬──────────────────────────────────────────────────────────┐
│  Retinode    │                                                          │
│              │                     MAIN STAGE                            │
│ ○ Patch      │   (whichever step is active; the canvas lives here)      │
│ ● Array      │                                                          │
│ ○ Tissue     │                                                          │
│ ○ Stimulus   │                                                          │
│ ○ Run        │                                                          │
│ ─────────    │                                                          │
│ ▸ Compare    │                                                          │
│ ▸ Study      │                                                          │
│ ▸ Validation │                                                          │
│ ▸ Candidates │                                                          │
│              │                                                          │
│ [tier badge] │                                                          │
│ [safety]     │                                                          │
└──────────────┴──────────────────────────────────────────────────────────┘
```

## 15. Screen by screen

**Patch.** Define the retinal population: density and types of RGCs, the axon-trajectory model toward the optic disc, or load specific morphologies. The canvas shows somas and the axon bundles they form. This is set once and mostly left alone, so it opens with a sensible default patch and hides the detail.

**Array (geometry).** The heart of the design loop. The retinal patch is the backdrop; electrodes are draggable disks on it. A grid generator makes arrays parametrically (pitch, rows and columns, square or hex, electrode size and shape, including honeycomb), and individual electrodes can be nudged, resized, or reshaped. Templates offer known layouts as starting points. This screen only edits physical geometry; currents are not here, keeping the geometry-versus-configuration line clean.

**Tissue and backend.** Choose the conductivity model (homogeneous for speed, layered for accuracy) and the field backend and tier. This is where the two-speed reality is set: pick analytical for live preview, FEM for accuracy. Advanced users set layer conductivities and mesh resolution; everyone else takes the defaults.

**Stimulus (configuration).** Assign which electrodes source and which return, and their currents, either by picking a pattern (monopolar, local return, bi-electrode) or by hand, or by setting a target cell and asking the optimizer for a steering pattern. The waveform lives here. As you edit, the preview field updates live.

**Run and monitor.** For analytical, results are already live. For FEM, this is where you launch the accurate job, watch progress, and see the cost estimate beforehand. Jobs are async and resumable; you can leave and come back.

**Results.** Three linked views over one configuration. A **field view**: the Ve heatmap with isopotential contours over the patch, electrodes and somas and bundles overlaid, with a slice control for depth and an optional 3D scene. An **activation view**: a slider over stimulus amplitude that lights up cells and axons as current rises, the target highlighted, the selective operating window drawn as the band where only the target fires. A **scorecard**: operating window, thresholds, charge density with its safety verdict, activated area, and the tier and sensitivity badges.

**Compare.** Several configurations on the same patch and metric, side by side, with their fields and scorecards aligned so differences are obvious. This is where "local return beats monopolar" becomes something you see, not just a number.

**Study and Pareto.** Build a sweep by choosing parameters to vary and ranges (electrode size, pitch, return radius, steering weights). See the cost estimate, launch, and watch an incrementally-filling table and a **selectivity-versus-cost Pareto frontier**. Click any point to inspect that configuration's field and activation. Overlay studies to compare families of designs.

**Validation.** The trust panel. Which published reproductions currently pass, with the figures. How the backends agree on shared problems. This screen is unusual and deliberate: it lets a skeptical labmate check the tool's credibility before believing its rankings.

**Candidates.** The payoff. A ranked, safety-filtered shortlist of configurations worth testing in tissue, each with predicted selectivity, threshold, charge verdict, accuracy tier, trajectory sensitivity, and a one-line rationale. Exportable as a report and as a machine-readable list for the lab. This screen is the reason the program exists, so it is designed to be handed to someone.

## 16. Visualization specifics

The field heatmap and isopotential contours, the activation animation over amplitude, and the Pareto and threshold plots are the workhorses. Two-dimensional views carry most of the load because they are legible and fast; a 3D scene is available for the field and the array but is secondary, since 3D often impresses more than it informs. Interaction is consistent: hover for values, click to inspect, brush to select on the Pareto plot. Every plot is exportable at figure quality, because half the point is putting these in front of the lab.

## 17. Frontend technology and staging

Staged so the tool is usable early and polished later, exploiting the engine's UI-independence:

- **Early, usable (Phase 2).** A Python-native dashboard (Dash, Panel, or Streamlit) that calls the engine directly and gives forms plus Plotly field and activation and Pareto views. Minimal frontend effort, good enough to validate the UX and be genuinely usable on the fast analytical tier.
- **Later, clean (Phase 6).** If the tool proves worth productizing, a FastAPI backend and a React frontend, with react-three-fiber for the 3D scene and a real charting layer for the 2D views, built to the instrument-panel visual language. This is the "looks clean and is easy to use" product, and because the engine and specs are unchanged, it is a re-skin of a working tool, not a rewrite of the science.

The recommendation is to resist building the polished app until the engine is trustworthy. A beautiful UI over an unvalidated engine is worse than a plain UI over a correct one, because it invites belief the numbers have not earned.

---

# Part V. How it all fits together

## 18. A full journey, end to end

Trace one path to see every component engage. A user opens a project (persistence loads the specs and cache). They accept the default patch and lay out a hex array on the Array screen; each edit mutates the geometry spec, and the app requests a live preview. The API calls the engine: the analytical field backend returns a cached-or-fresh transfer matrix, the evaluator scores selectivity with the cable engine's thresholds, and the field and scorecard render, badged analytical. The user tries a local-return configuration on the Stimulus screen; because the array is unchanged, the transfer matrix is reused and only the weighted sum and thresholds recompute, so the preview updates at once. Satisfied, they switch the backend to FEniCSx and hit Run accurately; the job model queues an FEM solve, streams progress, caches the new transfer matrix keyed to this geometry, and the results re-render badged FEM, with a note where the FEM answer diverged from the analytical one. They open Study, sweep return radius and pitch, see the cost estimate, launch, and watch the Pareto frontier fill; the engine reuses transfer matrices across configurations and recomputes fields across geometries, in parallel. They check Validation to confirm the tool still reproduces Fan 2019 and that FEniCSx and Sim4Life agree. They open Candidates, where the top safety-passing configurations are ranked with rationale and tiers, and export the report for Michael. Every step read or wrote the same spec objects; every result is reproducible from its provenance record.

## 19. The invariants that keep it coherent

Three rules, stated so they are not violated under pressure. The spec objects are the only source of truth, so no component invents its own representation. The transfer matrix is the only handoff between field and cable, so backends stay swappable. And every result is tagged with its accuracy tier and provenance, so nothing is trusted beyond what produced it. If a future change would break one of these, it is a redesign, not a patch.

---

# Part VI. Revised implementation plan

Phased so a usable, validated tool exists as early as possible and grows in capability and polish. Phases 0 to 3 are the **summer target**: a validated, usable tool on the analytical tier with a clean-enough dashboard. Phases 4 to 8 are the **fall and in-lab arc**: FEM accuracy, scale, the polished app, the geometry study, and release. The reproduce-then-extend spine runs through all of it; validation is never deferred to buy speed.

### Phase 0: Foundations
Repo, environment, and CI. Design and freeze the spec objects (geometry, configuration, conductivity, patch, study), their validation, serialization, and hashing. Implement the analytical field backend against the transfer-matrix contract. Stand up the test harness with the linearity property test. **Done when** specs round-trip to JSON and hash stably, and the analytical field passes its property tests.

### Phase 1: Cable engine and evaluator
The NEURON population engine with multi-site activation and threshold search, and the fixed evaluator (operating window, thresholds, charge density, activated area). Validate single-cell thresholds against Tsai 2012 and Greenberg 1999. **Done when** the analytical-plus-NEURON pipeline produces defensible thresholds and a selectivity score for any spec, matched to the literature on single cells.

### Phase 2: The minimal usable app
A Python dashboard over the engine: the Patch, Array, Tissue, Stimulus, and Results screens on the analytical tier, with the live preview loop and the field, activation, and scorecard views. This is where UX is first validated, cheaply, before FEM. **Done when** someone who is not you can design an array, set a configuration, and read a selectivity result without touching code.

### Phase 3: Reproduce the published results (credibility hinge)
Use the tool to recover the local-return selectivity gain (Fan 2019), bi-electrode axon avoidance (Vilkhu 2021), and multi-electrode nonlinearity (Vilkhu 2025), and wire these into regression tests and a first Validation screen. **Done when** the reproductions pass in CI and are visible in the app. This is the strong, complete stopping point for the summer: a usable, validated testbed.

### Phase 4: FEM accuracy layer
The FEniCSx backend behind the existing contract, the NGSolve backend as its cross-check, and Sim4Life as an independent field-only check, with a documented COMSOL adapter stub. Cross-backend agreement tests. Map where analytical can be trusted. **Done when** an open-source FEM backend is validated and drop-in, confirmed by a second backend, with the analytical-versus-FEM regime mapped. Heavier work, suited to lab compute.

### Phase 5: Study engine and compute scaling
The sweep engine, cost estimation, parametric FEM, optional surrogate model, parallel and cluster and cloud execution, resumable jobs, and the result cache at scale. **Done when** a geometry sweep runs to a Pareto frontier, reusing transfer matrices and recomputing fields per geometry, without manual bookkeeping.

### Phase 6: The polished application
If warranted, the FastAPI-plus-React app to the instrument-panel visual language, with the full screen set, the Compare and Study and Pareto and Candidates views, figure-quality visualization, and export. **Done when** the tool is clean, keyboard- and mobile-respectful, and pleasant enough to hand to a labmate.

### Phase 7: The geometry study and validation dashboard
Use the accurate engine to compare geometries systematically, producing the Pareto frontier and a defensible design finding, reported with tier and trajectory sensitivity, and complete the Validation dashboard. **Done when** there is a one-sentence, robust design finding backed by the frontier, and the trust panel is complete.

### Phase 8: Packaging, docs, and release
A pip-installable engine and app, documentation, reproducibility guarantees, and a public repo with a clear README and examples. **Done when** a stranger can install it, reproduce a headline result with one command, and read how to use it.

## 20. Dependencies and the critical path
Phase 0 blocks everything. Phase 1 needs Phase 0. Phase 2 needs Phase 1 for real results but its screens can be scaffolded against Phase 0. Phase 3 needs Phases 1 and 2. Phase 4 needs the Phase 0 contract and nothing else, so FEM can be prototyped in parallel once the contract is frozen. Phase 5 needs Phase 4. Phases 6 and 7 need 4 and 5. Phase 8 is last. The one hard serialization is spec then engine then validation; the UI and FEM can proceed in parallel once the spec is frozen.

---

# Part VII. Risks, limits, and what to cut

**Accuracy ceiling.** Even at Tier 2 this is a screening and hypothesis tool, not an oracle; novel rankings can sit inside the model's error, so they ship with tier and sensitivity and are framed as candidates for tissue testing. This limit is stated in the interface, not hidden.

**FEM learning curve and compute.** FEniCSx and NGSolve meshing and convergence take real time, and geometry sweeps are heavy. Mitigations: keep the analytical tier fully capable so the summer does not depend on FEM, and defer heavy sweeps to lab compute.

**UI scope creep.** The biggest schedule risk is polishing the app before the engine is trustworthy. Mitigation: the staged frontend, and the rule that the polished app waits until validation passes. If time is short, the Python dashboard is the shippable UI and the React app is cut without loss of science.

**Backend divergence.** Swappable backends can quietly model different things. Mitigation: the neutral geometry spec and the cross-backend agreement tests, which turn divergence into a failing test rather than a silent error.

**What to cut under pressure, in order.** The React app (keep the dashboard), the 3D scene (keep 2D), the surrogate model (accept slower sweeps), current-steering optimization (keep fixed-configuration comparison). The irreducible core that must survive any cut: the spec, the analytical field, the validated cable engine and evaluator, the reproductions, and a usable interface over them.

---

# Part VIII. Deliverables and the pitch

**Deliverables.** A UI-independent engine with swappable field backends behind one contract; a validated cable-and-evaluator pipeline; reproductions of the lab's local-return, bi-electrode, and multi-electrode results wired into CI and a validation dashboard; a study engine and a geometry Pareto frontier with a defensible finding; a clean application with geometry editing, field and activation visualization, comparison, and a safety-checked candidate export; and a documented, installable, reproducible public repo.

**The pitch.** "I built a testbed that lets you design an epiretinal electrode configuration, simulate how selectively it activates ganglion cells, and screen many geometries against a selectivity-and-safety score, validated against the lab's own local-return and multi-electrode results, with every result carrying its accuracy tier. It outputs a ranked shortlist of configurations worth testing in tissue." That is a tool the lab's geometry and current-steering work, and Michael's shelved project, can actually use, and it is the thing you would build together.
