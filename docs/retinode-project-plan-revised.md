# Comprehensive Design and Implementation Plan
## An epiretinal electrode-geometry selectivity testbed (Retinode)

This is a planning document. It designs the whole program — engine, application, and interface — and how the parts fit, and it lays out a revised, phased build order. It does not implement anything. The aim is a tool accurate enough to be trusted, clean enough to be pleasant, and easy enough that someone who is not you (Michael, a labmate) can sit down and use it to find electrode configurations worth testing in tissue.

Three commitments shape every decision below:

1. **Accurate.** Reproduce known results before trusting novel ones; make every result carry its accuracy tier and its sensitivity; treat safety as a first-class output.
2. **Usable.** A fast design loop, sensible defaults, progressive disclosure, and trust made visible.
3. **Honest.** The tool screens and generates hypotheses. It proposes configurations for ex vivo or in vivo testing. It is not, from simulation alone, a ground-truth oracle, and it says so in its own interface.

The scientific ground this stands on is real and recent, mostly from the Chichilnisky lab's own ex vivo primate work: local returns sharpen selectivity (Fan et al. 2019), bi-electrode patterns can steer current around axon bundles (Vilkhu et al. 2021), and multi-electrode currents combine *nonlinearly* through multi-site activation (Vilkhu et al. 2025). Those three results are simultaneously the tool's validation targets and its reason to exist: if the tool can reproduce them, it can be trusted to screen the geometries nobody has tested yet. Full citations are collected in Part IX.

### A note on terminology (read this first)

The whole design hinges on one distinction, so it is worth stating before anything else:

- **Geometry** is the *physical* array: electrode sizes, shapes, positions, pitch, and placement over the retina. Changing geometry requires re-solving the field.
- **Configuration** (or *stimulus*) is the *current delivery*: which electrodes source and which return, with what weights and waveform, over a fixed geometry. Changing configuration is cheap — it is a weighted sum over an already-solved field.

A handful of other terms recur and mean exactly one thing throughout: the **transfer matrix** (the field each electrode produces per unit current, the universal handoff between solvers and cells), the **selective operating window** (the current range over which only the target cell fires), the **off-target set** (the explicit list of non-target cells and axons a score is measured against), and the **accuracy tier** (analytical, FEM, or cross-checked, attached to every number). These are defined precisely where they are first used and consolidated in the glossary (Part X).

---

# Part I. What the program is

## 1. Vision and scope

**One sentence.** Retinode lets a user specify a hypothetical epiretinal electrode geometry and current configuration, simulate how it activates a population of retinal ganglion cells and their axons of passage, score its selectivity and safety, compare it against alternatives, and export a ranked shortlist of configurations worth testing in tissue.

**In scope.** Epiretinal, direct RGC and axon-of-passage activation. Physical electrode geometry (size, shape, pitch, placement) and current configuration (which electrodes source and return, with what weights, including current steering). A field engine with swappable backends across accuracy tiers. A selectivity-and-safety evaluator. A study engine for parameter sweeps. A clean application with geometry editing, field and activation visualization, comparison and Pareto views, a validation dashboard, and candidate export.

**Out of scope (for now, stated so it does not creep).** Subretinal or suprachoroidal stimulation (different physics, different cell targets). Percept prediction — that is pulse2percept's job (Beyeler et al. 2017), and a one-way bridge to it is a possible later add, not a goal. Closed-loop hardware control. Patient-specific anatomy. Manufacturing and fabrication modeling beyond electrode geometry. Chronic effects, electrode degradation, and encapsulation. Temporal pulse-train dynamics beyond the single-pulse threshold (adaptation, desensitization) are out of scope for the summer and flagged as a known limitation.

**Audience.** You first. Then lab members who want to screen a geometry idea without writing simulation code. The second audience is why the UI matters: the tool has to be legible to someone who understands retinas but not your codebase.

## 2. Users and core journeys

The design is anchored on a small set of journeys. Everything in the UI exists to serve one of these.

- **Design and preview.** Lay out an electrode array over a retinal patch, set a current configuration, and immediately see the field and a fast selectivity estimate. Iterate quickly.
- **Run accurately.** Promote a promising design from the fast analytical preview to an accurate FEM run, and see how the answer changes.
- **Compare.** Put several configurations side by side, on the same patch and metric, and see which wins and why.
- **Sweep and find the frontier.** Define a study that varies geometry or configuration parameters across ranges, run it, and read the selectivity-versus-cost Pareto frontier.
- **Trust.** Check, in the interface, which published results the tool currently reproduces and how backends agree, so the numbers are believable.
- **Hand off.** Export a ranked, safety-checked shortlist of candidate configurations, with rationale and accuracy caveats, ready to discuss with the lab and test in tissue.

Two personas keep these honest. **You** are the power user: you will touch conductivity layers, mesh resolution, and trajectory distributions, and you care about provenance. **Michael** is the screening user: he wants to open the tool, pick a template, try an idea, and get a defensible number and a picture, without reading source. Every screen is designed so Michael's path is the default and your path is one disclosure deeper.

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

Concretely, the package layout mirrors the layers, so the dependency direction is enforced by imports rather than discipline alone:

```
retinode/
  engine/            # pure library; no fastapi, no plotly, no dash imports
    spec/            # domain model, validation, serialization, hashing
    field/           # transfer-matrix contract + backends
    cable/           # NEURON population + threshold search
    eval/            # the fixed evaluator
    study/           # sweep + surrogate + cost model
    store/           # cache, project store, provenance
    validate/        # property tests, cross-backend, reproductions
  api/               # FastAPI; imports engine, never the reverse
  app/               # dashboard (Phase 2) then React client (Phase 6)
  tests/
```

A single lint rule — `engine/` may not import from `api/` or `app/` — is worth a CI check, because this one boundary is what makes the Phase 6 re-skin a re-skin and not a rewrite.

---

# Part III. Component design (engine)

## 5. Domain model and the spec

The spec is the set of serializable objects that describe a simulation completely. Design and freeze their interfaces before building anything on top — this is the keystone. There are five:

- **ElectrodeArray** (geometry): a list of electrode primitives, each with an id, a 3D position, a shape (`disk`, `square`, `hex`, or a polygon boundary), a size, and a facing normal; plus array-level metadata (units, coordinate frame). Carries **no current**.
- **StimConfig** (configuration): a map from electrode id to a complex/real weight, a designated return set (or `distant` for monopolar), and a waveform (biphasic pulse: cathodic-first, phase width, interphase gap, amplitude scale). Carries **no geometry** beyond referencing electrode ids.
- **ConductivityModel**: either `homogeneous` (a single σ) or `layered` (ordered slabs with per-layer σ and thickness, optional anisotropy tensor). Retinal tissue is mildly anisotropic; the model allows it but defaults to isotropic.
- **RetinalPatch**: RGC soma positions and types, per-cell morphology (or a parametric morphology model), axon trajectories toward the optic disc, and a designated target cell. Carries the index that maps field query points back to per-cell compartments.
- **StudyDefinition**: names the parameters to vary (dotted paths into the specs above), their ranges or grids, the backend/tier to run at, and the objective(s) to record.

A compact sketch, to make the shape concrete (illustrative, not final):

```python
@dataclass(frozen=True)
class Electrode:
    id: str
    pos_um: tuple[float, float, float]   # microns, patch frame
    shape: Literal["disk","square","hex","poly"]
    size_um: float                        # diameter or edge; poly uses boundary
    normal: tuple[float,float,float] = (0,0,1)

@dataclass(frozen=True)
class ElectrodeArray:
    electrodes: tuple[Electrode, ...]
    frame: str = "patch"                  # coordinate convention
    schema_version: int = 1
    # invariant: electrode ids unique; no current fields anywhere
```

**Responsibilities of this layer.** Strict validation, stable serialization, and content hashing.

- *Validation* rejects, with a clear message: duplicate electrode ids; a configuration whose currents do not charge-balance to within tolerance (∑ weights ≈ 0, required for a safe biphasic stimulus); a configuration referencing an electrode the array does not contain; a patch with no target cell; overlapping electrodes; a layered conductivity whose slabs do not span the patch depth. Validation is a pure function `validate(spec) -> list[Problem]`, so the API and the UI surface identical errors.
- *Serialization* is canonical JSON: keys sorted, floats round-tripped losslessly, enums as strings, `schema_version` on every object so old projects migrate forward.
- *Hashing* is SHA-256 over the canonical JSON of each object and of composite keys (see §10). Because geometry and configuration are separate objects, their hashes are separate, which is exactly what lets the cache reuse a field across configurations.

The terminology distinction is enforced *structurally*, not by convention: geometry objects have no current field and configuration objects have no position field, so the two cannot blur even under a careless edit.

## 6. Field engine

One contract makes solvers interchangeable: **given an array, a conductivity model, and a set of query points, return the extracellular potential each electrode produces at those points, per unit current, as a transfer matrix.** Linearity of the quasi-static Laplace problem (∇·(σ∇V) = −I source, no time dependence at these frequencies) means one unit-current solve per electrode suffices, and any configuration is a weighted sum.

Formally, for `m` query points and `n` electrodes the backend returns **A ∈ ℝ^(m×n)** where `A[i,j]` is the potential at point `i` from a unit current on electrode `j`. Then for any configuration with current vector **I ∈ ℝ^n**, the extracellular potential is simply

```
Ve = A · I          # (m,) volts, given A in V/A and I in A
```

That single matrix is the universal handoff: the cable engine never sees the solver, only `Ve` sampled at its compartments.

**Backends, by accuracy tier.**

- **Tier 1 — analytical (point/disk source).** For a point source in an infinite homogeneous medium, `Ve(r) = I / (4πσr)`; a finite disk electrode uses the standard disk-source potential (equipotential-disk solution) so near-field values are not singular. Fast enough for the live preview and for prototyping. This is the workhorse of the summer.
- **Tier 2 — FEM (FEniCSx primary, NGSolve cross-check).** Solves the Laplace problem on a meshed geometry with real electrode boundaries and layered conductivity. FEniCSx/DOLFINx is the primary open-source backend; NGSolve solves the same gmsh mesh independently and must agree within tolerance. This is the geometry study's engine and is deferred to lab compute.
- **Tier 3 — independent check (Sim4Life, COMSOL later).** Sim4Life is a field-only cross-check with its own solver, run in the cloud and returning a file the pipeline imports as an `A` matrix; COMSOL is a thin adapter for the lab later. Swappability rests on a **neutral geometry spec** (electrode primitives plus conductivity slabs) that each backend meshes its own way, with gmsh as the shared mesh for the open-source solvers.

**Design concerns this layer owns.**

- *Caching.* The transfer matrix is keyed by `hash(array, conductivity, query-point set, backend, backend-params)` so a fixed array-and-tissue is never re-solved. This is the single biggest performance lever (see §9).
- *The honest boundary.* Changing physical geometry requires a new solve; changing configuration does not. The API and UI make this boundary visible rather than hiding it (§12, two-speed).
- *Mesh independence.* No FEM number is trusted before a convergence check: refine the mesh until the metric of interest (target threshold, or `Ve` at the soma) changes by less than a set tolerance between refinements. The convergence curve is stored with the result so the claim is auditable.
- *Units and sign conventions,* fixed once and asserted in tests: positions in microns, currents in microamps, potential in millivolts at the cable layer, cathodic current negative. A surprising fraction of stimulation bugs are sign and unit errors; the property tests (§11) pin these down.

## 7. Cable and population engine

This is the scientific heart, and the reason a linear field alone is not enough. NEURON-backed multi-compartment RGC models are placed in the patch, driven by the field through NEURON's `extracellular` mechanism (the transfer-matrix `Ve` is applied as the extracellular potential at each compartment), with a per-cell **bisection threshold search** on stimulus amplitude.

**Membrane model.** RGC excitability uses the Fohlmeister–Miller channel set — the five voltage- and ion-gated conductances established for ganglion cells: fast sodium (I_Na), calcium (I_Ca), delayed-rectifier potassium (I_K), A-type potassium (I_K,A), and calcium-activated potassium (I_K,Ca) (Fohlmeister & Miller 1997; the compartmental stimulation form follows Greenberg et al. 1999). Channel densities differ by compartment class — soma, dendrites, axon hillock, sodium-channel band, and axon — because the low-threshold sodium-channel band near the axon hillock is precisely what governs where a spike initiates, and therefore what selective stimulation must exploit or avoid.

**Multi-site activation — the property the lab cares about most.** A spike initiating at *any* compartment counts as activation. This is exactly why multi-electrode currents combine nonlinearly: two subthreshold electrodes can each depolarize a different region of the same cell and jointly cross threshold, or depolarize different cells, in a way no single-site linear proxy captures. Running the full cable model rather than a single-site linear surrogate is what keeps multi-electrode predictions honest, and reproducing this nonlinearity (Vilkhu et al. 2025) is a Phase 3 validation target.

**Axons of passage and the activating function.** Off-target activation of axons crossing the patch is the central selectivity problem, because an axonal spike produces a smeared, non-focal percept. Whether an axon fires is governed to first order by Rattay's **activating function**, proportional to the second spatial derivative of `Ve` along the axon (∂²Ve/∂x²); bi-electrode patterns that flatten that second derivative along bundles are how Vilkhu et al. (2021) achieved axon avoidance. The engine therefore (a) models axon trajectories explicitly as compartments, not just somata, and (b) exposes the activating function along each axon as a diagnostic the evaluator and UI can use. Because thresholds are sensitive to the ascending axon path, the engine averages over a **distribution of trajectories** per cell rather than committing to one guessed path, and reports the spread.

**The subthreshold shortcut, clearly labeled.** For fast screening only, a reciprocity/lead-field approximation estimates activation from the field and a precomputed per-cell sensitivity (the cell's "electrical receptive field") without a full NEURON solve. It accelerates sweeps but is explicitly a Tier-1 estimate: the full bisection threshold search remains the ground truth, and any candidate promoted toward tissue testing is re-scored with the full model.

**Design concerns.** Mapping field query points to per-cell compartments (the patch provides the index); sensible spike-detection criteria and time windows; a bisection tolerance and amplitude bracket that are recorded with each threshold; and validation of single-cell thresholds against the literature (Tsai et al. 2012; Greenberg et al. 1999) before any population-level number is believed.

## 8. Evaluator

One fixed scorer, called identically for every configuration so comparisons are apples to apples. Freezing the scorer's definition is as important as freezing the spec: a metric that drifts silently invalidates every comparison made before the drift. It produces:

- **Selective operating window (SOW).** The current gap between the lowest off-target threshold and the target's threshold: `SOW = I_off_min − I_target`. Positive when a range of amplitudes fires *only* the target; the primary selectivity metric, in microamps. The window is also reported as a ratio (`I_off_min / I_target`) so it is comparable across cells of different absolute sensitivity.
- **Thresholds.** Target threshold and the full vector of off-target thresholds, each with the trajectory-distribution spread from §7.
- **Charge density and safety verdict.** Charge per phase `Q = |I|·PW` per active electrode and charge density `Q/A` against a limit. Safety is judged by the Shannon criterion, `log(D) = k − log(Q)` with a conservative `k ≤ 1.5` (Shannon 1992; McCreery et al. 1990), *and* against the electrode material's own charge-injection limit. A configuration that exceeds either is flagged and **excluded from any candidate shortlist** — the whole point is proposing things for real tissue.
- **Activated area / cell count.** The spatial extent and number of cells brought to threshold, the complement of selectivity.

**The off-target set is an explicit modeling choice**, recorded with every result: which neighboring somata (by radius or count) and which bundle axons (by proximity to the array) are counted as off-target. It shapes the numbers, and Michael will have opinions about it, so it is a first-class, editable field rather than a buried constant. Two configurations may only be compared if their off-target sets and evaluator version match; the evaluator refuses mismatched comparisons rather than producing a misleading number.

## 9. Efficiency and compute

Two speeds, matching the two kinds of sweep, and the split falls directly out of the geometry/configuration distinction.

- **Configuration sweeps on a fixed array** reuse one transfer matrix `A` and cost only a weighted sum plus threshold searches — cheap enough to run live. A steering sweep over hundreds of weight vectors on a fixed array is a Tier-1 interactive operation.
- **Physical-geometry sweeps** recompute the field per geometry and are expensive, so they run as batched, parametric FEM jobs, coarse-to-fine, optionally with a **surrogate model** (a Gaussian-process or similar emulator over the selectivity score as a function of geometry parameters) that proposes where to sample next once enough points exist.

A thin **job model** wraps every long run (FEM solves, NEURON threshold searches, sweeps) as an async task with progress callbacks, a job store, and resumability, so nothing blocks and nothing is lost on a crash. Execution adapters cover local (a process pool), cluster (Slurm on Stanford's FarmShare or Sherlock through a sponsoring lab), and cloud (Sim4Life). The API exposes job status and streams progress to the UI.

**Cost estimation lives here too, and it is a safety feature for the user's time.** Before a study runs, estimate `n_field_solves × per_solve_time` (from a quick benchmark on the actual mesh) plus `n_configs × per_threshold_time`, and surface the total, so no one accidentally launches a three-day job. The estimate, and the realized time, are both logged so the estimator improves.

## 10. Persistence and provenance

A **project** is a saved workspace: its specs, study definitions, cached transfer matrices (HDF5 or npz), results (a columnar store like parquet plus JSON for nested fields), and a provenance log. The on-disk layout is deliberately boring and inspectable:

```
project.retinode/
  specs/            # canonical JSON, one file per spec, hash in filename
  cache/fields/     # A matrices, keyed by field-hash, HDF5
  results/          # parquet (scalar metrics) + JSON sidecars (curves)
  provenance.log    # append-only, one record per run
  project.json      # manifest: schema versions, created/updated, index
```

**Every run records** the full spec (by hash and by value), the software versions (NEURON, the FEM backend, Retinode itself), the git commit, the random seeds, the mesh-convergence evidence for FEM runs, and timestamps — so any figure can be regenerated and any result traced to exactly what produced it. The **result cache** is keyed by content hashes composed across geometry, configuration, conductivity, patch, backend, and parameters, so re-runs and overlapping sweeps reuse work automatically:

```
field_key  = H(array, conductivity, query_points, backend, backend_params)
result_key = H(field_key, config, patch, evaluator_version, eval_params)
```

Note that `result_key` includes `field_key`, so touching geometry correctly invalidates the field *and* everything downstream, while touching only the configuration reuses the field — the cache encodes the honest boundary from §6. Reproducibility is therefore not bolted on at the end; it falls out of the spec-as-source-of-truth plus disciplined hashing.

## 11. Validation and test harness

Correctness is the product, so testing is part of the architecture, not a chore. Four layers of test, all in CI:

- **Unit tests** per component (validation rejects the right specs, serialization round-trips, the disk-source formula matches a known value).
- **Property tests that assert the physics.** *Linearity:* the field of a sum of currents equals the sum of the fields, `A·(I₁+I₂) = A·I₁ + A·I₂`. *Reciprocity* where it should hold. *Superposition and units:* doubling all currents doubles `Ve`; sign conventions hold. These catch whole classes of bug that example-based tests miss.
- **Cross-backend agreement tests** that fail if two solvers disagree beyond tolerance on a shared problem (FEniCSx vs NGSolve on the same mesh; analytical vs FEM in the regime where they should match). Divergence becomes a failing test, not a silent modeling error.
- **Regression tests that reproduce the literature** and break the build if a change silently degrades them: local-return selectivity gain (Fan et al. 2019), bi-electrode axon avoidance (Vilkhu et al. 2021), and multi-electrode nonlinearity (Vilkhu et al. 2025), plus single-cell threshold sanity against Tsai et al. (2012) and Greenberg et al. (1999). Each reproduction stores the target quantity, the tolerance, and the current value.

These same checks feed the **validation dashboard** in the UI (§15), so the tool's trustworthiness is both enforced in CI and visible to the user. A published result that the tool reproduces in CI and shows in the app is worth more than any amount of assurance in prose.

---

# Part IV. UI/UX design

The interface has to do something unusual: make an accurate, compute-heavy scientific tool feel light. The guiding ideas below all serve that.

## 12. UX principles

- **Two-speed by design.** Editing the geometry or configuration updates a fast analytical **preview** instantly, so the design loop never stalls. Accurate FEM is an explicit **Run accurately** action that queues an async job. The UI never pretends FEM is instant, and it never blocks on it. Concretely: preview responses target well under a second (they are a cached `A` times a new `I`, plus thresholds), and the same result surface re-renders in place when the FEM job returns, with a visible diff against the analytical estimate.
- **Trust made visible.** Every result carries a small **tier badge** (analytical, FEM, Sim4Life-checked) and, where relevant, a sensitivity note (the trajectory-distribution spread from §7). A validation panel shows which published results currently reproduce and how backends agree. The user should be able to see why to believe a number.
- **Safety inline.** Charge density against the electrode limit is shown wherever a configuration is, with anything unsafe flagged in place and kept out of candidate lists. Safety is never a separate screen you have to remember to check.
- **Progressive disclosure.** Strong defaults and templates up front (a standard array, a standard patch, a monopolar configuration), with advanced parameters (conductivity layers, mesh resolution, off-target definitions, trajectory distributions) tucked into expandable panels. Michael's path never requires opening one.
- **One vocabulary.** The precise terminology holds everywhere: geometry means the physical array, configuration means current delivery. Colors mean one thing throughout — a cool field color for potential, a warm signal color for activation, a distinct alert color for safety limits — reusing the instrument-panel identity so the whole project feels like one thing.
- **Reproducibility as UX.** Any view can be saved, shared, and reopened to exactly its state, because it is just a spec plus a result reference. A shared link *is* a hash.
- **Quality floor.** Responsive down to a laptop, visible keyboard focus, reduced motion respected, honest empty and error states that say what to do next. The validation errors from §5 surface here verbatim, so the message a user sees is the message the engine wrote.

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

The persistent tier and safety badges in the rail are always-on trust indicators: wherever you are, you can see what accuracy you are looking at and whether the current configuration is safe.

## 15. Screen by screen

Each screen edits or reads exactly one part of the spec, which keeps the mental model and the data contract aligned.

**Patch.** Define the retinal population: density and types of RGCs, the axon-trajectory model toward the optic disc, or load specific morphologies. The canvas shows somas and the axon bundles they form. Set once and mostly left alone, so it opens with a sensible default patch and hides the detail. *Edits:* `RetinalPatch`.

**Array (geometry).** The heart of the design loop. The retinal patch is the backdrop; electrodes are draggable disks on it. A grid generator makes arrays parametrically (pitch, rows and columns, square or hex, electrode size and shape, including honeycomb), and individual electrodes can be nudged, resized, or reshaped. Templates offer known layouts as starting points. This screen edits *only* physical geometry; currents are not here, keeping the geometry-versus-configuration line clean. *Edits:* `ElectrodeArray`.

**Tissue and backend.** Choose the conductivity model (homogeneous for speed, layered for accuracy) and the field backend and tier. This is where the two-speed reality is set: pick analytical for live preview, FEM for accuracy. Advanced users set layer conductivities and mesh resolution; everyone else takes the defaults. *Edits:* `ConductivityModel`, backend selection.

**Stimulus (configuration).** Assign which electrodes source and which return, and their currents, either by picking a pattern (monopolar, local return, bi-electrode) or by hand, or by setting a target cell and asking the optimizer for a steering pattern. The waveform lives here. As you edit, the preview field updates live. *Edits:* `StimConfig`.

**Run and monitor.** For analytical, results are already live. For FEM, this is where you launch the accurate job, watch progress, and see the cost estimate beforehand (§9). Jobs are async and resumable; you can leave and come back.

**Results.** Three linked views over one configuration. A **field view**: the `Ve` heatmap with isopotential contours over the patch, electrodes and somas and bundles overlaid, a slice control for depth and an optional 3D scene. An **activation view**: a slider over stimulus amplitude that lights up cells and axons as current rises, the target highlighted, the selective operating window drawn as the band where only the target fires, and the activating function optionally overlaid along a selected axon. A **scorecard**: operating window, thresholds, charge density with its safety verdict, activated area, and the tier and sensitivity badges.

**Compare.** Several configurations on the same patch and metric, side by side, with their fields and scorecards aligned so differences are obvious. This is where "local return beats monopolar" becomes something you *see*, not just a number. The evaluator's refusal to compare mismatched off-target sets (§8) surfaces here as a clear, actionable warning rather than a silent apples-to-oranges chart.

**Study and Pareto.** Build a sweep by choosing parameters to vary and ranges (electrode size, pitch, return radius, steering weights). See the cost estimate, launch, and watch an incrementally-filling table and a **selectivity-versus-cost Pareto frontier**. Click any point to inspect that configuration's field and activation. Overlay studies to compare families of designs.

**Validation.** The trust panel. Which published reproductions currently pass, with the figures; how the backends agree on shared problems. This screen is unusual and deliberate: it lets a skeptical labmate check the tool's credibility before believing its rankings.

**Candidates.** The payoff. A ranked, safety-filtered shortlist of configurations worth testing in tissue, each with predicted selectivity, threshold, charge verdict, accuracy tier, trajectory sensitivity, and a one-line rationale. Exportable as a report and as a machine-readable list for the lab. This screen is the reason the program exists, so it is designed to be handed to someone.

## 16. Visualization specifics

The field heatmap and isopotential contours, the activation animation over amplitude, and the Pareto and threshold plots are the workhorses. Two-dimensional views carry most of the load because they are legible and fast; a 3D scene is available for the field and the array but is secondary, since 3D often impresses more than it informs. Interaction is consistent: hover for values, click to inspect, brush to select on the Pareto plot. Every plot is exportable at figure quality (SVG/PDF for vector, high-DPI PNG for raster), because half the point is putting these in front of the lab.

**The data contract for a view is small and explicit.** A field view needs the query-point grid, the `Ve` array, the electrode outlines, and the soma/axon overlays; an activation view needs, per amplitude step, the set of firing compartments and the target flag; a scorecard needs the evaluator's scalar outputs and badges. Each is a plain JSON payload the engine already computes, so the same contract serves the Phase-2 dashboard and the Phase-6 React client unchanged — the migration re-skins the renderer, not the data.

## 17. Frontend technology and staging

Staged so the tool is usable early and polished later, exploiting the engine's UI-independence:

- **Early, usable (Phase 2).** A Python-native dashboard (Dash, Panel, or Streamlit — leaning Dash/Plotly for interaction fidelity) that calls the engine directly and gives forms plus Plotly field, activation, and Pareto views. Minimal frontend effort, good enough to validate the UX and be genuinely usable on the fast analytical tier.
- **Later, clean (Phase 6).** If the tool proves worth productizing, a FastAPI backend and a React frontend, with react-three-fiber for the 3D scene and a real charting layer for the 2D views, built to the instrument-panel visual language. Because the engine and specs are unchanged and the view data contracts (§16) are fixed, this is a re-skin of a working tool, not a rewrite of the science.

The recommendation is to resist building the polished app until the engine is trustworthy. A beautiful UI over an unvalidated engine is worse than a plain UI over a correct one, because it invites belief the numbers have not earned.

---

# Part V. How it all fits together

## 18. A full journey, end to end

Trace one path to see every component engage. A user opens a project (persistence loads the specs and cache). They accept the default patch and lay out a hex array on the Array screen; each edit mutates the geometry spec, and the app requests a live preview. The API calls the engine: the analytical field backend returns a cached-or-fresh transfer matrix, the evaluator scores selectivity with the cable engine's thresholds, and the field and scorecard render, badged analytical. The user tries a local-return configuration on the Stimulus screen; because the array is unchanged, the transfer matrix is reused and only the weighted sum and thresholds recompute, so the preview updates at once. Satisfied, they switch the backend to FEniCSx and hit **Run accurately**; the job model queues an FEM solve, streams progress, caches the new transfer matrix keyed to this geometry, and the results re-render badged FEM, with a note where the FEM answer diverged from the analytical one. They open Study, sweep return radius and pitch, see the cost estimate, launch, and watch the Pareto frontier fill; the engine reuses transfer matrices across configurations and recomputes fields across geometries, in parallel. They check Validation to confirm the tool still reproduces Fan 2019 and that FEniCSx and Sim4Life agree. They open Candidates, where the top safety-passing configurations are ranked with rationale and tiers, and export the report for Michael. Every step read or wrote the same spec objects; every result is reproducible from its provenance record.

## 19. The invariants that keep it coherent

Three rules, stated so they are not violated under pressure:

1. **The spec objects are the only source of truth**, so no component invents its own representation.
2. **The transfer matrix is the only handoff between field and cable**, so backends stay swappable.
3. **Every result is tagged with its accuracy tier and provenance**, so nothing is trusted beyond what produced it.

If a future change would break one of these, it is a redesign, not a patch — and the reviewer's job on any pull request is to check these three before anything else.

---

# Part VI. Revised implementation plan

Phased so a usable, validated tool exists as early as possible and grows in capability and polish. Phases 0 to 3 are the **summer target**: a validated, usable tool on the analytical tier with a clean-enough dashboard. Phases 4 to 8 are the **fall and in-lab arc**: FEM accuracy, scale, the polished app, the geometry study, and release. The reproduce-then-extend spine runs through all of it; validation is never deferred to buy speed.

### Phase 0: Foundations
Repo, environment, and CI. Design and freeze the spec objects (geometry, configuration, conductivity, patch, study), their validation, serialization, and hashing. Implement the analytical field backend against the transfer-matrix contract. Stand up the test harness with the linearity property test. **Done when** specs round-trip to JSON and hash stably, and the analytical field passes its property tests.

### Phase 1: Cable engine and evaluator
The NEURON population engine with multi-site activation and threshold search, and the fixed evaluator (operating window, thresholds, charge density, activated area). Validate single-cell thresholds against Tsai et al. (2012) and Greenberg et al. (1999). **Done when** the analytical-plus-NEURON pipeline produces defensible thresholds and a selectivity score for any spec, matched to the literature on single cells.

### Phase 2: The minimal usable app
A Python dashboard over the engine: the Patch, Array, Tissue, Stimulus, and Results screens on the analytical tier, with the live preview loop and the field, activation, and scorecard views. This is where UX is first validated, cheaply, before FEM. **Done when** someone who is not you can design an array, set a configuration, and read a selectivity result without touching code.

### Phase 3: Reproduce the published results (credibility hinge)
Use the tool to recover the local-return selectivity gain (Fan et al. 2019), bi-electrode axon avoidance (Vilkhu et al. 2021), and multi-electrode nonlinearity (Vilkhu et al. 2025), and wire these into regression tests and a first Validation screen. **Done when** the reproductions pass in CI and are visible in the app. This is the strong, complete stopping point for the summer: a usable, validated testbed.

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

## 20. The summer schedule (Phases 0–3)

A concrete, week-by-week plan for the summer target, anchored to today (Monday, July 13, 2026) and running ten weeks to a mid-September stop before the fall term. Effort assumes roughly full-time focus (~35 h/week); the estimates are deliberately conservative, with slack folded into a final buffer week rather than hidden inside each task. NEURON is the single biggest unknown, so Phase 1 gets the most room.

| Week | Dates | Phase | Focus | Milestone / gate |
|------|-------|-------|-------|------------------|
| 1 | Jul 13–19 | 0 | Repo, env, CI; draft and stress-test the spec objects; validation + canonical JSON + hashing | Specs round-trip and hash stably |
| 2 | Jul 20–26 | 0 | Analytical field backend (point/disk source) against the transfer-matrix contract; linearity property test | **Gate 0:** analytical field passes property tests; spec frozen |
| 3 | Jul 27–Aug 2 | 1 | NEURON RGC model up: Fohlmeister–Miller channels, compartment classes, `extracellular` drive | Single cell spikes correctly under an imposed field |
| 4 | Aug 3–9 | 1 | Bisection threshold search; single-cell threshold validation vs Tsai 2012 / Greenberg 1999 | Single-cell thresholds match literature within tolerance |
| 5 | Aug 10–16 | 1→2 | Population placement, multi-site activation, axon trajectories; freeze the evaluator; begin dashboard scaffold | **Gate 1:** pipeline yields a defensible selectivity score for any spec |
| 6 | Aug 17–23 | 2 | Dashboard: Patch/Array/Tissue/Stimulus/Results on the analytical tier; live preview loop | **Gate 2:** a non-coder designs an array and reads a score |
| 7 | Aug 24–30 | 3 | Reproduce Fan 2019 (local-return selectivity gain); wire into regression test + Validation screen | Fan 2019 reproduced in CI and visible in app |
| 8 | Aug 31–Sep 6 | 3 | Reproduce Vilkhu 2021 (bi-electrode axon avoidance) via the activating function | Vilkhu 2021 reproduced |
| 9 | Sep 7–13 | 3 | Reproduce Vilkhu 2025 (multi-electrode nonlinearity); complete first Validation screen | **Gate 3:** all three reproductions green in CI and in app |
| 10 | Sep 14–20 | — | Buffer, write-up, demo, and lab hand-off; tag a summer release | Summer deliverable complete |

The critical, unmovable milestones are the four gates. If a week slips, the buffer absorbs it; if more than the buffer slips, the cut list in §24 says what to drop, in order, and the tool is still a complete story at whichever gate it reaches — Gate 2 alone is a usable design tool, and Gate 3 is the validated testbed that justifies the whole project.

## 21. Dependencies and the critical path

Phase 0 blocks everything. Phase 1 needs Phase 0. Phase 2 needs Phase 1 for real results but its screens can be scaffolded against Phase 0. Phase 3 needs Phases 1 and 2. Phase 4 needs the Phase 0 contract and nothing else, so FEM can be prototyped in parallel once the contract is frozen. Phase 5 needs Phase 4. Phases 6 and 7 need 4 and 5. Phase 8 is last. The one hard serialization is **spec → engine → validation**; the UI and FEM can proceed in parallel once the spec is frozen. This is why freezing the spec at the end of Week 2 (Gate 0) is the highest-leverage moment in the whole schedule: everything downstream forks from it, and every day the spec stays fluid is a day nothing built on it is safe.

---

# Part VII. Risks, limits, and what to cut

## 22. Principal risks and mitigations

**Accuracy ceiling.** Even at Tier 2 this is a screening and hypothesis tool, not an oracle; novel rankings can sit inside the model's error, so they ship with tier and sensitivity and are framed as candidates for tissue testing. This limit is stated in the interface, not hidden.

**NEURON schedule risk (the summer's true long pole).** Getting the Fohlmeister–Miller model, compartment geometry, and `extracellular` drive to produce literature-matching thresholds is the least predictable task, and Phases 2 and 3 depend on it. Mitigations: it gets two full weeks (3–4) plus slack in Week 5; single-cell validation against Tsai 2012 / Greenberg 1999 is an explicit Week-4 checkpoint so trouble surfaces early; and if it overruns, a published channel implementation is adopted rather than built from the paper.

**FEM learning curve and compute.** FEniCSx and NGSolve meshing and convergence take real time, and geometry sweeps are heavy. Mitigations: keep the analytical tier fully capable so the summer does not depend on FEM, and defer heavy sweeps to lab compute (FarmShare/Sherlock).

**UI scope creep.** The biggest schedule risk after NEURON is polishing the app before the engine is trustworthy. Mitigation: the staged frontend, and the rule that the polished app waits until validation passes. If time is short, the Python dashboard is the shippable UI and the React app is cut without loss of science.

**Backend divergence.** Swappable backends can quietly model different things. Mitigation: the neutral geometry spec and the cross-backend agreement tests, which turn divergence into a failing test rather than a silent error.

**Reproduction mismatch.** A published result might not reproduce within tolerance — because of a genuine modeling gap or a misread of the paper's conditions. Mitigation: treat each reproduction as an experiment with a written-down expected quantity and tolerance; a near-miss is a finding to understand and document, not a failure to hide, and the Validation screen shows the current value against the target either way.

## 23. Decision gates (go / no-go)

Each gate is a go/no-go with a defined fallback, so a slip is a decision, not a scramble:

- **Gate 0 (end Wk 2) — spec frozen, analytical field validated.** *Go:* start NEURON. *No-go:* the spec is still churning — stop and finish it; nothing downstream is safe until it holds.
- **Gate 1 (end Wk 5) — pipeline produces defensible thresholds.** *Go:* build the dashboard. *No-go:* thresholds don't match literature — stay on the cable engine; adopt a reference channel implementation; do not build UI over numbers you don't trust.
- **Gate 2 (end Wk 6) — a non-coder can use it.** *Go:* start reproductions. *No-go:* UX blocks a naive user — fix the smallest set of blockers only; do not gold-plate.
- **Gate 3 (end Wk 9) — three reproductions green.** *Go:* the summer deliverable is done; write up and, if time remains, begin Phase 4 FEM prototyping. *No-go:* one reproduction misses — ship the two that pass, document the third as an open finding; the tool is still a validated testbed.

## 24. What to cut under pressure, in order

The cut list is ordered so that each cut removes the most scope for the least loss of science:

1. The React app (keep the dashboard).
2. The 3D scene (keep the 2D views).
3. The surrogate model (accept slower sweeps).
4. Current-steering optimization (keep fixed-configuration comparison).
5. The third reproduction (ship two, document the third as open).

**The irreducible core that must survive any cut:** the spec, the analytical field, the validated cable engine and evaluator, at least the Fan 2019 reproduction, and a usable interface over them. Below that, it is not the tool this document describes.

---

# Part VIII. Deliverables and the pitch

**Deliverables.** A UI-independent engine with swappable field backends behind one contract; a validated cable-and-evaluator pipeline; reproductions of the lab's local-return, bi-electrode, and multi-electrode results wired into CI and a validation dashboard; a study engine and a geometry Pareto frontier with a defensible finding; a clean application with geometry editing, field and activation visualization, comparison, and a safety-checked candidate export; and a documented, installable, reproducible public repo.

**What "done" looks like, measurably.** Single-cell thresholds within tolerance of Tsai 2012 / Greenberg 1999; all three lab reproductions green in CI; a non-coder completing the design-to-score loop unaided; every result in the app carrying a tier badge and a safety verdict; and any exported figure regenerable from its provenance record with one command.

**The pitch.** "I built a testbed that lets you design an epiretinal electrode configuration, simulate how selectively it activates ganglion cells, and screen many geometries against a selectivity-and-safety score — validated against the lab's own local-return and multi-electrode results, with every result carrying its accuracy tier. It outputs a ranked shortlist of configurations worth testing in tissue." That is a tool the lab's geometry and current-steering work, and Michael's shelved project, can actually use, and it is the thing you would build together.

---

# Part IX. References

Verified against the primary literature. The three lab results in the first group are simultaneously the scientific motivation and the Phase-3 validation targets.

**Epiretinal selectivity — the lab's ex vivo primate results.**

1. Fan VH, Grosberg LE, Madugula SS, Hottowy P, Dabrowski W, Sher A, Litke AM, Chichilnisky EJ. "Epiretinal stimulation with local returns enhances selectivity at cellular resolution." *Journal of Neural Engineering* 16(2):025001, 2019. doi:10.1088/1741-2552/aaeef1
2. Vilkhu RS, Madugula SS, Grosberg LE, Gogliettino AR, et al., Chichilnisky EJ. "Spatially patterned bi-electrode epiretinal stimulation for axon avoidance at cellular resolution." *Journal of Neural Engineering* 18(6):066007, 2021. doi:10.1088/1741-2552/ac3450
3. Vilkhu R, Vasireddy PK, Kish K, Gogliettino AR, Lotlikar A, Hottowy P, Dabrowski W, Sher A, Litke AM, Mitra P, Chichilnisky EJ. "Understanding responses to multi-electrode epiretinal stimulation using a biophysical model." *Journal of Neural Engineering* 22(1):016010, 2025. doi:10.1088/1741-2552/ada1fe

**RGC biophysics, models, and thresholds.**

4. Fohlmeister JF, Miller RF. "Impulse encoding mechanisms of ganglion cells in the tiger salamander retina." *Journal of Neurophysiology* 78(4):1935–1947, 1997. (The five-channel RGC membrane model: I_Na, I_Ca, I_K, I_K,A, I_K,Ca.)
5. Greenberg RJ, Velte TJ, Humayun MS, Scarlatis GN, de Juan E Jr. "A computational model of electrical stimulation of the retinal ganglion cell." *IEEE Transactions on Biomedical Engineering* 46(5):505–514, 1999.
6. Tsai D, Chen S, Protti DA, Morley JW, Suaning GJ, Lovell NH. "Responses of retinal ganglion cells to extracellular electrical stimulation, from single cell to population: model-based analysis." *PLOS ONE* 7(12):e53357, 2012. doi:10.1371/journal.pone.0053357

**Stimulation biophysics and safety.**

7. Rattay F. "Analysis of models for external stimulation of axons." *IEEE Transactions on Biomedical Engineering* BME-33(10):974–977, 1986. (The activating function: activation ∝ ∂²Ve/∂x² along the axon — the basis of the bi-electrode axon-avoidance logic.)
8. Shannon RV. "A model of safe levels for electrical stimulation." *IEEE Transactions on Biomedical Engineering* 39(4):424–426, 1992. (The charge-density/charge-per-phase safety criterion, log D = k − log Q.)
9. McCreery DB, Agnew WF, Yuen TG, Bullara L. "Charge density and charge per phase as cofactors in neural injury induced by electrical stimulation." *IEEE Transactions on Biomedical Engineering* 37(10):996–1001, 1990.

**Perception bridge (out-of-scope reference, for a possible later add).**

10. Beyeler M, Boynton GM, Fine I, Rokem A. "pulse2percept: A Python-based simulation framework for bionic vision." *Proceedings of the 16th Python in Science Conference (SciPy)*, 2017. doi:10.25080/shinma-7f4c6e7-00c

**Further reading (Chichilnisky-lab context, relevant to thresholds and steering).**

11. "Inference of electrical stimulation sensitivity from recorded activity of primate retinal ganglion cells." *Journal of Neuroscience* 43(26):4808, 2023.
12. "A scalable framework for current steering at single-neuron resolution." *bioRxiv* 2025.03.14.643392 (preprint). Relevant to the current-steering optimizer (§15, Stimulus).

**Core software (versions are pinned in every provenance record, §10).**

13. Hines ML, Carnevale NT. "The NEURON simulation environment." *Neural Computation* 9(6):1179–1209, 1997.
14. The FEniCS Project / DOLFINx (FEniCSx) — open-source finite-element solver, primary FEM backend.
15. Schöberl J. NGSolve — finite-element library, FEM cross-check backend.
16. Geuzaine C, Remacle J-F. "Gmsh: a three-dimensional finite element mesh generator with built-in pre- and post-processing facilities." *International Journal for Numerical Methods in Engineering* 79(11):1309–1331, 2009.

---

# Part X. Glossary and key formulas

For a labmate opening this cold. Terms are used with exactly these meanings throughout.

- **Geometry.** The physical electrode array: sizes, shapes, positions, pitch, placement. Changing it requires a new field solve.
- **Configuration (stimulus).** The current delivery over a fixed geometry: which electrodes source/return, weights, waveform. Changing it is a cheap weighted sum.
- **Transfer matrix (A).** `A[i,j]` = extracellular potential at query point `i` per unit current on electrode `j`. The universal handoff between field solvers and the cable engine. `Ve = A · I`.
- **Accuracy tier.** The provenance of a number: Tier 1 analytical, Tier 2 FEM, Tier 3 independently cross-checked (Sim4Life/COMSOL). Attached to every result.
- **Multi-site activation.** A spike may initiate at any compartment of a cell; this is why multi-electrode currents combine nonlinearly and why the full cable model is required.
- **Activating function.** ∝ ∂²Ve/∂x² along an axon (Rattay 1986); predicts where an axon is driven toward firing, and what a bi-electrode pattern must flatten to avoid axon activation.
- **Selective operating window (SOW).** `I_off_min − I_target`: the current range over which only the target fires. Positive is good; the primary selectivity metric.
- **Off-target set.** The explicit, recorded list of non-target somata and bundle axons a score is measured against. Comparisons are only valid within a fixed off-target set.
- **Charge per phase / charge density.** `Q = |I|·PW`; density `Q/A`. Judged against the Shannon criterion (`log D = k − log Q`, conservative `k ≤ 1.5`) and the electrode material limit. Failing either excludes a configuration from the candidate list.
- **Spec.** The five serializable objects (`ElectrodeArray`, `StimConfig`, `ConductivityModel`, `RetinalPatch`, `StudyDefinition`) that fully describe a simulation and serve as API payload, on-disk format, and cache key.

Key relations, in one place: `Ve = A·I` (field); activation when a compartment crosses threshold under `Ve` (cable); `SOW = I_off_min − I_target` (selectivity); `log D = k − log Q`, `k ≤ 1.5` (safety); `result_key = H(field_key, config, patch, evaluator_version, eval_params)` and `field_key = H(array, conductivity, query_points, backend, backend_params)` (caching, which encodes the geometry/configuration boundary).

---

# Part XI. Open questions and decisions to lock with the lab

A planning honesty check: these are the modeling choices the numbers are sensitive to, and they should be decided *with* the lab (with Michael, especially the off-target set) before Phase 3, not defaulted silently. Each is cheap to change while the spec is fluid and expensive after.

- **Conductivity.** Homogeneous σ for the summer, or layered from the start? What σ value(s), and is anisotropy worth modeling at Tier 1? (Affects every threshold.)
- **Off-target set.** Which somata (radius or count) and which bundle axons count as off-target? This shapes the SOW more than almost anything else and is Michael's call.
- **Cell types and morphology.** Which RGC types (parasol, midget) and densities, and parametric versus traced morphologies? Which compartment channel densities?
- **Axon trajectories.** Which trajectory model toward the optic disc, and how many samples per cell to characterize the threshold spread?
- **Waveform and threshold definition.** Standard biphasic pulse width and polarity; and is "threshold" a deterministic crossing or a 50%-activation probability (the ex vivo data are probabilistic)?
- **Electrode material and limits.** Which material (platinum, sputtered iridium oxide) sets the charge-injection limit, and which Shannon `k` (1.5 conservative vs 1.85)?
- **Default array template.** Which template ships as the default — matched to the lab's 512-electrode arrays (10 µm electrodes, 30–60 µm pitch) used in the results being reproduced?

Locking these seven is the natural first conversation with the lab, and doing it before Gate 0 is what lets the spec freeze on schedule.

