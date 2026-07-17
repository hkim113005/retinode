# Phase 7 — Design specification: an instrument, not a dashboard

> **Interactive mockup of the Results screen:** [`docs/mockups/results-screen.html`](mockups/results-screen.html)
> (self-contained; open in a browser). Drag the amplitude dial to watch cells bloom
> as they cross threshold, toggle Analytical↔FEM to see tier-as-texture, and read the
> operating-window band on the dial. It demonstrates the signature patterns below in
> the locked instrument-panel palette (light + dark). This is a design study, not
> wired to the engine.

**North star.** The interface should feel like a **bench instrument** the user reads
fluently — an oscilloscope for electrode design — not a web dashboard they operate.
Every pixel earns its place by carrying information or making the next move obvious.
The UI must be *as trustworthy and precise as the engine underneath it*: what you
see is exactly what was computed, at the accuracy it was computed, and you can always
see why to believe it.

This extends — never replaces — the established visual language (master plan §13):
graphite ink on a cool light ground, **one cool accent (blue) for interaction and
the potential field**, **one warm accent (amber) reserved for activation and
completion**, a distinct alert for safety, hairline structure, glass cards, dark-mode
aware. Restraint everywhere except one signature moment. The tokens are already in
`app/assets/style.css` and are locked.

---

## The two readers

Every decision is judged against two people at once:

- **Michael** (a labmate, non-coder): opens the app, takes the defaults, and must
  reach a believable answer without opening a single advanced panel.
- **The expert** (the lab, later you): wants density, keyboard speed, provenance, and
  the ability to audit any number.

The resolution is not a "simple mode" toggle — it is **progressive density**: the
surface reads calm at a glance and rewards inspection. Michael sees a clean field and
a scorecard; the expert sees the same screen and reads six sparklines, a tier
texture, and a hash chip. Same pixels, different depth.

---

## The signature: one living canvas

The field-and-activation canvas is the hero (master plan §13). Make it a genuine
instrument, not a chart:

- **The amplitude dial drives everything.** A single horizontal control — styled like
  a scope's sweep — scrubs stimulus amplitude. As you drag it up, cells **bloom
  warm** the instant they cross threshold; the target is ringed; axons of passage
  light along their length. This turns an abstract threshold number into a physical
  *watch-it-fire* moment. Dragging down un-fires them. The dial is the page's center
  of gravity.
- **The selective operating window is drawn, not stated.** As amplitude rises, a lit
  **band** appears on the dial spanning "target fires" to "first bystander fires" —
  the selective window, shown as the range where only the target is lit. Its width
  *is* the selectivity. A safety ceiling is a red tick on the same dial. One control
  carries threshold, selectivity, and safety at once.
- **Isopotential contours are labeled.** The `Ve` heatmap (cool) underlays the cells,
  and contour lines carry their mV value inline — color for the gestalt, numbers for
  the read. Never a legend you have to cross-reference.

Everything else on the page stays quiet so this canvas carries it.

---

## One spatial frame, never reloaded

The retinal patch — somas and the axon bundles they form — is the **constant
backdrop on every screen** (Array, Stimulus, Results, Compare). Electrodes, field,
and firing all overlay the *same* coordinate frame at the same scale. The user never
re-orients.

Switching screens does **not** reload the canvas — it **morphs**: electrodes fade in
on Array, the field blooms on Results, a second config slides in on Compare. Spatial
continuity is the single biggest "feels like one instrument" lever, and it is nearly
free once the canvas is one component reading one frame.

---

## Trust you can see (tier as texture)

Trust is ambient, not a panel you remember to check:

- **Tier is a texture, not just a badge.** An **analytical** result is drawn slightly
  *draft* — hairline contours, a touch desaturated, like a pencil sketch. An **FEM**
  result is *inked* — crisp, saturated, solid. You can tell the accuracy of a number
  from across the room, before reading its badge. When an FEM job completes, the
  canvas **settles** from draft to inked in one quiet transition — the only "job
  done" signal you need.
- **Where FEM disagreed with analytical, the canvas says so** — a small "Δ vs
  analytical" marker at the point of largest divergence, so the upgrade in accuracy
  is legible, not silent.
- **The persistent rail badges** (tier · safety) are always-on, wherever you are.

## Safety inline, never a screen

Charge density rides with every configuration as a small **inline gauge** that fills
toward a red line. Under the limit it is quiet; crossing it, the number turns alert
**in place** and the configuration is visually **struck** and dropped from Candidates
automatically. Safety is never a tab you have to open (master plan §12).

---

## Compare is a difference, not two charts

Side-by-side is table stakes; the creative move is to **compute the comparison for
the user**:

- **A signed-difference field.** Overlay two configs as one heatmap of *where config
  A's field beats B's* — "local return beats monopolar" becomes a shape you see, in a
  diverging cool/warm scale centered on zero.
- **A delta column.** Scorecards align with a **Δ column**: Δ selectivity, Δ
  threshold, Δ safe-window, each signed and colored. The win is a number you read,
  not a comparison you perform. The evaluator's refusal to compare mismatched
  off-target sets surfaces here as an **actionable banner** ("these use different
  bystander sets — align them?"), never a silent apples-to-oranges chart.

---

## Study: the Pareto frontier as a decision surface

> **Interactive mockup:** [`docs/mockups/study-pareto-screen.html`](mockups/study-pareto-screen.html)
> — hover a design to ghost its field, drag a box across the frontier to select a
> family, and hit *Run study* to watch the frontier fill incrementally.

The selectivity-versus-cost frontier is the hero of Study (master plan §15):

- **Dominated points recede; the frontier is a lit curve.** Non-optimal designs draw
  faint; the Pareto set is a bright arc you read as a shape.
- **Hover ghosts the field.** Hovering a point blooms a **thumbnail field** in the
  corner — a sparkline-scale preview — so you feel each design without clicking.
- **Brush selects a family, and the selection flows to Candidates.** Drag a box on the
  frontier; those designs become the Candidates shortlist. Selection is a first-class,
  portable object.
- **Axes speak human.** "µA to fire the target" vs "bystanders also firing," not raw
  metric names. The cost estimate shows *before* you launch (master plan §9), and the
  table fills incrementally as jobs return.

## Scanning families: small multiples

Compare and Study lean on **small-multiple field thumbnails** (Tufte): a row of tiny,
labeled fields lets the eye scan a whole family at once, full field one click away.
This is how the tool stays "optimal for information" — many designs visible
simultaneously, drill-down on demand, no modal reloads.

---

## The 3D loupe (secondary, always at hand)

3D "impresses more than it informs" (master plan §16), so it is **not a mode**. It is
a small **loupe** docked in the corner of the field canvas, showing the array's true
3D form — bodies, tilt, imported CAD, and any cell/electrode **overlap flag** — so you
glance at geometry intuition without leaving the 2D truth. Click to expand it full-
bleed; it collapses back. The loupe is where Phase 6's 3D geometry becomes visible
without stealing the page.

---

## Reproducibility as a visible affordance

"A shared link *is* a hash" (master plan §12), made tangible:

- Every view carries a small **◇ state chip** with its short hash. Click it → the
  shareable link is on your clipboard; reopening it restores the exact state.
- Hovering the chip opens a **provenance peek**: the exact spec inputs and result
  lineage behind this number, so a skeptic audits any figure in two moves without
  leaving the view. Reproducibility stops being a promise and becomes a button.

---

## Depth on demand (progressive disclosure that labels itself)

Advanced parameters (mesh resolution, conductivity layers, off-target sets,
trajectory spread) live behind a **consistent expander in the same place on every
screen** — and each expander shows a **one-line summary of what it hides**
(`mesh: auto · σ: homogeneous · bystanders: 6`). You always know what you're *not*
looking at. Michael's path never opens one; the expert flicks them open by habit.

---

## The keyboard spine

Expert speed without visual clutter: a **⌘K command palette** jumps screens, loads
templates, runs jobs, toggles tier, and exports. Every action is reachable by
keyboard; focus is always visible (quality floor, §12). The palette keeps power off
the surface — the newcomer never sees it, the expert never touches the mouse.

---

## Honest states that teach

Empty and error states name the next move, in the instrument's own voice:

- Empty Compare: *"No configuration yet — start monopolar, or load a template,"* each
  a button.
- The engine's own validation messages surface **verbatim** in the alert color with
  the fix as an action, so the message the user sees is the message the engine wrote
  (master plan §12).

## Motion with meaning

One signature motion — the **activation bloom** as cells fire — plus tiny state
transitions (draft→inked on job completion, a config striking out on a safety
breach). Everything else is near-instant. Motion always *encodes a state change*,
never decoration, and `prefers-reduced-motion` collapses it to instant swaps.

---

## Information density, concretely

Being "optimal for information" is a set of habits, not a slogan:

- **Sparkline everything inline** — thresholds, the activating function along an axon,
  charge density, the biphasic waveform (a tiny scope trace in the Stimulus
  controls). A number rarely appears without its shape beside it.
- **The scorecard is one dense, scannable band**, not a stack of stats: the operating
  window as a horizontal axis with the target threshold, each off-target threshold,
  and the safety ceiling as tick marks — the whole selectivity story in one line.
- **Use the full dynamic range** of the field colormap and always offer the numeric
  read (hover for value); color for gestalt, digits for truth.
- **No decorative chrome.** Hairlines and whitespace do the structuring the master
  plan already commits to; every card that exists carries data.

---

## The color vocabulary (locked)

| Meaning | Token | Use |
|---|---|---|
| Potential / interaction | `--accent` (blue) | the `Ve` field, links, focus, selected |
| Activation / completion | `--warn` (amber) | firing cells, job-done, the operating-window band |
| Safe | `--ok` (green) | charge-density under limit, passing validation |
| Alert / limit | alert red | safety breach, blocking errors, the safety-ceiling tick |
| Structure | `--ink` / `--muted` / hairline `--border` | text, labels, dividers |

Colors mean exactly one thing throughout, so the whole tool reads as one instrument
(master plan §13). A firing cell and a completed job share amber because both are
"the signal arrived"; the field and a hyperlink share blue because both are "potential
to act."

---

## How this lands in the P7 build

This spec is the acceptance bar for the phase-7-plan.md steps, not new scope:

- **S2 (Compare screen)** ships the living canvas, the amplitude dial + activation
  bloom, the operating-window band, tier-as-texture, and the inline safety gauge.
- **S3 (jobs)** makes draft→inked the completion signal.
- **S4 (Study)** ships the Pareto decision surface, ghost-field hover, brush→
  Candidates, and small multiples.
- **S5 (3D)** ships the loupe, not a separate screen.
- **S6 (Candidates/Validation)** inherits the scorecard band, tier badges, and the
  provenance chip. Interactive mockup:
  [`docs/mockups/candidates-screen.html`](mockups/candidates-screen.html) — the ranked
  shortlist opens with the one-sentence recommendation, each row carrying its
  operating-window band, tier texture, trajectory-sensitivity whisker, and export.
- **S7 (charts/export)** ships labeled contours, sparklines, and figure-quality
  vector/raster export of every plot.
- **S8 (polish)** ships the ⌘K spine, teaching empty/error states, reduced-motion, and
  the one-vocabulary audit.

The bar: a labmate should be able to *read* this instrument on first sight, and an
expert should never wish it were denser or faster.
