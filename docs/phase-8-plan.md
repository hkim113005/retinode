# Phase 8 — Closing Phase 7's deferrals (and the defect they hid)

**Goal.** Close the four items Phase 7 left deferred: the activation-vs-amplitude and
threshold plots, native PDF export, per-candidate trajectory sensitivity, and
unstranding Phase 6's 3D capability in the UI. No new science was planned — this was
meant to be finishing work over the engine and contract already built.

**What actually happened.** It was not finishing work. Each deferral was **scouted
against the real code before building** (four read-only agents in parallel), and every
one came back different from its note — two of them were mislabelled by *me* in the
Phase-7 write-ups. The load-bearing outcome was a **product-level defect the deferrals
surfaced**: the analytical field tier is blind to electrode geometry, which had
quietly made the entire Study/Candidates premise flat by construction. That took over
the phase.

The engine's physics is unchanged; what changed is **which tier the geometry study
runs on**, three new **view contracts** (per-cell thresholds, the amplitude sweep, the
trajectory spread), and a set of **honesty corrections** to claims that did not hold.

Detailed measurements and the reasoning behind the decisions live in
[phase-8-findings.md](phase-8-findings.md); this is the *what was built* record.

---

## Method: scout before building

Every slice below began with a read-only agent auditing the relevant engine/contract
code and reporting what actually existed, versus what the deferral note assumed. This
is why the phase found defects instead of just shipping features: the notes were a
Phase-7-era guess, and the code had moved (or the guess was wrong). The pattern is
worth keeping — **a deferral note is a hypothesis, not a spec.**

---

## Steps

- **P8 S1 — Activation-vs-amplitude + threshold plots — done.** Two plots the
  scorecard's numbers had earned but never showed.

  - *Threshold plot* — pure plumbing. `off_min_uA` was a `min()` over a per-cell
    threshold vector the evaluator already computed and `api/service.py` was
    collapsing on the way out. The contract now carries the vector
    (`ScorecardResponse.off_target_thresholds_uA`, `limiting_off_id`); the plot lays
    every cell on one current axis with the selective window as a band and the charge
    limit as a wall. *Verified live:* on a 10 µm disk it showed the bystander closing
    the window at 24.6 µA barely ahead of the charge limit at 24.9 — a near-coincidence
    the scorecard's separate rows never made visible.
  - *Activation curve* — a real engine function, `engine/study/activation.amplitude_sweep`.
    The threshold search probes ~20 amplitudes per cell and keeps only the crossing;
    this sweeps a stated grid and keeps the whole answer (who fires, where the spike
    initiates, whether a cell blocks at high current). Same cost order as the
    scorecard — the field is solved once per cell, every amplitude is a matvec — and
    unlike a bisection it reports honest per-amplitude progress. `SolvedPopulation` was
    **promoted** (not copied) so the sweep and the threshold search share one placement
    path; it stays in `engine/study` because moving it to `engine.cable.population`
    would close an import cycle.
  - *Refused, deliberately:* no "activation fraction" (the patch is a handful of cells,
    so a fraction is a step function pretending to be a sigmoid); `crossing_uA` is
    never called a threshold (it is grid resolution; the bisection is the accurate
    number, and the plot draws both so you can see they agree).
  - *Live verification earned its keep:* the first default grid was **linear** over
    1–200 µA, which on real NEURON put **both cells on the same grid point** (12.7 µA)
    and reported a zero-wide window. Thresholds live at the bottom of that range; the
    grid and the plot axis are both **logarithmic** now, separating them at 8.9 and
    16.5 µA. The linear grid was not merely uglier — it was wrong.

- **P8 S2 — Native PDF export — assessed and dropped, not built.** D8 promised
  "SVG/PDF". PDF was assessed in full and deliberately dropped, for reasons better than
  the deferral note's (which claimed "SVG already reaches PDF" — false; SVG is not a
  journal format):

  1. It cannot be built honestly at this scope — the Pareto draws `→` and `◤`, outside
     PDF's base-14 glyph coverage, so a shippable writer substitutes glyphs and becomes
     the **first renderer that does not draw what the screen drew**, breaking the one
     invariant S7a exists to hold.
  2. It buys nothing — figure assembly happens in Illustrator/Inkscape regardless, and
     the SVG→PDF step is absorbed into that, not added to it.
  3. A dependency (`pdf-lib`/`jspdf`) is +110–150 KB gzip on a 60 KB app and is base-14
     too, so it doesn't even solve (1).
  4. No test oracle — a PDF's correctness can't be asserted in jsdom, leaving a hole in
     an otherwise fully-covered layer.

  D8's wording was amended to promise **vector (SVG) + high-DPI raster (PNG)**, which is
  what is delivered and what the acceptance bar (`phase-7-design.md`) always asked for.

- **P8 S3 — Per-candidate trajectory sensitivity — done.** The deferred column, once it
  was clear it means the **axon-trajectory distribution** (`engine/cable/trajectories.py`,
  already built and tested), **not array placement** — a mislabelling carried over from
  the Phase-7 note. `engine/study/spread.geometry_trajectory_spread` lifts the existing
  one-cell spread to a geometry sweep: the std of the target threshold over K sampled
  axon paths. Opt-in (`trajectory_k=1` = off, so nobody pays for a whisker they didn't
  ask for), surfaced as `StudyPoint.spread_uA`, drawn as a `±` beside the threshold,
  with a **Robustness** sort that disables itself when nothing measured the spread.
  `None` renders as *absent*, never a confident-looking `±0`.

  *Two real limits fell out of verifying it against the engine, both pinned by tests
  and written up in the findings doc:*
  1. **The analytical tier is blind to electrode geometry** (→ S4).
  2. **The whisker is exactly 0 in the default scene, correctly** — the perturbation
     rotates the axon about +z, a single driven electrode's field is symmetric about
     +z, and the target sits on that axis, so all K thresholds are identical. Honest
     and uninformative; it measures something only off the axis of symmetry.

- **P8 S4 — Force FEM for geometry sweeps — done (the phase's centre of gravity).**
  S3's verification found that `AnalyticalBackend` is a point source: it reads an
  electrode's position, never its extent, so **every diameter and pitch in a study
  produces a byte-identical field**. The Study screen's diameter × pitch frontier was
  flat by construction, and Candidates ranked noise. This was invisible through all of
  Phase 7 because every live check of Study used a **fake thresholds provider whose
  invented cost depended on diameter** — a dependence the real engine does not have.

  The user chose (of disk-model / honest-badge / force-FEM) to **force FEM**. Built as
  three green sub-slices:

  - *S4a — engine.* `resolve_field_tier`'s docstring corrected (point source, not
    "exact for a half-space"); `geometry_field_tier` (comparing geometry is always
    FEM), `geometry_varies`, and `require_geometry_distinguishable` — a diameter sweep
    on the analytical tier is now a **raised `GeometryTierError`**, not a silent flat
    frontier.
  - *S4b — API.* The study dispatches to the conda `retinode-fem` env (FEM field + real
    NEURON), mirroring the Phase-7 FEM field dispatch: `study_core` (FastAPI/Pydantic-
    free orchestration, plain dicts), `study_job` (conda entrypoint), `study_worker` (uv
    dispatcher, streaming `@@P` progress live so the minutes-long bar moves). The route
    splits on whether a provider was **explicitly injected** (dev/test → in-process,
    fast) versus the default (production → FEM dispatch) — "provider is None" couldn't
    tell them apart, because `create_app` defaults to the real provider.
  - *S4c — UI.* Study's badge reads **FEM**, the cost estimate is grounded in the
    measured ~28 s/geometry (a 4×4 sweep ≈ 8 min), and a note explains why geometry
    needs FEM.

  *Verified end-to-end, locally and in CI:* a 2-diameter study returns 9.49 µA (d10) vs
  10.20 µA (d30) — byte-identical on the analytical tier, distinct on FEM, in the
  physically sensible direction. The live run also forced a genuine engine fix (below).

---

## Defects fixed along the way

Three were found by *running the thing*, not by reading it — the argument for live
verification over trusting green unit tests:

1. **The z-convention landmine** (`app/scene.py`). Cells were placed at z = −20, against
   the Phase-6 convention (z = 0 array plane, +z into tissue). The analytical tier never
   noticed — its field is mirror-symmetric about z = 0, so no number moved (403 NEURON
   tests unchanged after the flip). But every Phase-6 3D predicate assumes +z
   (`point_in_body` tests `0 ≤ dz ≤ height`), so the first electrode to carry a body
   would have made the **overlap safety check silently match nothing**. Fixed at the
   source; `api/fem_job` was already papering over it with `abs()`.
2. **The FEM domain was too small for the cell.** It auto-sized to the array (~65 µm for
   a small electrode), but the field is sampled at the cell's compartments — the axon of
   passage reaches **378 µm** toward the optic disc, outside the mesh, a hard crash. Added
   a `min_half_width_um` floor through `default_domain` → `FenicsxBackend`; `study_core`
   floors it at the measured query reach × 1.15.
3. **A stale linear amplitude grid** (S1) that collapsed the operating window to zero on
   real NEURON — see S1.

## Honesty corrections (no behaviour change)

- Retracted a false claim I had written in P7 S5: the 3D loupe does **not** render
  bodies/tilt/CAD "when the geometry carries them" — the view contract is flat
  (`ElectrodeMarker` is x/y/radius), so no geometry can carry them and no such code
  exists. Corrected in `Loupe3D.tsx` and `phase-7-plan.md`.
- Amended D8's "SVG/PDF" to match what ships (S2).
- Corrected the trajectory-sensitivity deferral note (axon distribution, not placement).

---

## Testing & honesty

- **Fast (uv):** the plot scene builders (pure, fully testable), the contract round-
  trips, `study_core` + `study_worker` with a **mocked subprocess** (the streamed
  progress protocol, the result round-trip, honest failure when the FEM env is absent),
  and the geometry-tier guards.
- **NEURON (uv):** the amplitude sweep agrees with the bisection (the grid crossing
  brackets the searched threshold from above within one step); a single-geometry study
  runs real NEURON on the analytical tier.
- **FEM (conda `test-fem`):** the real 2-diameter FEM+NEURON study, asserting the two
  diameters produce **different** thresholds — the whole point of forcing FEM. This runs
  in CI's micromamba env and passed there.
- **Contract:** the OpenAPI snapshot + generated TS types stay in lockstep, as before.

Every defect and limit is pinned by a test so it cannot silently regress, and the two
irreducible limits (the analytical tier's disk-blindness residue for *pitch*/shaped/3D;
the zero-spread symmetry) are documented rather than tuned away.

---

## What remains open

- **A 3D body-authoring surface** — the original P8 S4 ("unstrand Phase-6 3D in the
  UI"). The scout concluded this is **a phase of its own, not a deferral**: it needs a
  body discriminated union in the contract, a per-electrode array builder, a new
  **Array design screen** (the inert Design-rail steps), a 3D renderer for four body
  types + tilt + CAD + overlap flags, and a new "unpreviewable geometry" interaction
  idiom (bodies are FEM-only, so they cannot live-preview — this breaks the design
  spec's live-instrument thesis and must be solved on paper first). Phase 8 delivered
  the prerequisite z-convention fix and retracted the false rendering claim; the editor
  itself is unbuilt.
- **Array-placement sensitivity** — "how much does the window degrade if the array is
  misplaced by a few µm or tilted?" A distinct, unbuilt idea (arguably more decision-
  relevant for a lab than axon-path epistemics), conflated once with S3. Needs a
  placement-perturbation sweep axis; tilt is FEM-only.
- **A cheap geometry tier** — the disk-model alternative to forcing FEM (Newman's
  oblate-spheroidal solution) was weighed and not taken; it would restore a fast tier
  that sees *diameter* but still not pitch or shaped/3D. On the table if FEM-cost Study
  proves too slow in practice.
- **Trajectory spread on the FEM tier** is coherent but expensive (K× the FEM cost per
  geometry) and exactly zero on the symmetric default scene; enabling it usefully needs
  an off-axis target or an elevation perturbation.
