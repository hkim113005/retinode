# Phase 8 — findings

Closing Phase 7's deferrals surfaced two limits that are bigger than the deferrals
were. Both are **pinned by tests** so they cannot be quietly forgotten again.

---

## 1. The analytical tier is blind to electrode geometry — so the Study sweep is flat

`AnalyticalBackend` is a **point source**: it reads an electrode's position, never its
extent. Measured directly (`tests/field/test_regime.py`):

| geometry | Ve @ target | Ve @ neighbour | safety ceiling |
|---|---|---|---|
| d=8 µm, pitch 30 | −7.95775 | −3.55881 | 19.93 µA |
| d=8 µm, pitch 70 | −7.95775 | −3.55881 | 19.93 µA |
| d=16 µm, pitch 30 | −7.95775 | −3.55881 | 39.87 µA |
| d=24 µm, pitch 70 | −7.95775 | −3.55881 | 59.80 µA |

**Every geometry produces a byte-identical field.** Diameter changes nothing;
pitch changes nothing (the protocol drives only the centre electrode, and the
undriven ones contribute no current). Only the **safety ceiling** moves, via charge
density over area.

The consequence is not subtle. The **Study screen sweeps diameter × pitch and plots a
selectivity-versus-cost frontier**. On the analytical tier — the default, and the tier
Candidates stamps on every exported row — every point collapses onto the same
coordinates. A real two-geometry run returns `threshold=8.31, window=4.51` for **both**
d10 and d20. The frontier is flat by construction, and the ranking it feeds is ranking
noise.

*This was invisible during Phase 7 because every live verification of Study used a
**fake thresholds provider** whose invented cost depended on diameter. The fake had a
geometry dependence the real engine does not.*

`docs/electrode-geometry.md` already says shaped and 3D electrodes are FEM-only and
that "the analytical tier is a point source". What nobody joined up: **that makes the
entire geometry-sweep premise FEM-only too.** `resolve_field_tier`
(`engine/study/geometry_sweep.py`) picks a tier from the **conductivity alone** —
homogeneous → analytical, "exact for a half-space". Exact for a *point source* in a
half-space. It has no notion that the electrode's own geometry might demand FEM.

**Options, none of them small:**

1. **Make `resolve_field_tier` geometry-aware** — force FEM when a sweep varies
   electrode extent. Honest, and makes Study an FEM-cost job (minutes, not seconds).
2. **Give the analytical backend a disk model** — a finite-disk potential
   (e.g. the classic oblate-spheroidal solution) instead of a point source. Restores a
   cheap tier that can actually see diameter; real physics work, and needs validating
   against FEM.
3. **Say so in the UI** — badge the frontier "diameter has no effect at this tier" and
   direct the user to FEM. Cheapest, and at least stops the screen implying an answer
   it cannot give.

Until one of these lands, **the Study and Candidates screens cannot answer the question
they are shaped around** ("which electrode diameter is most selective?") on the tier
they run.

---

## 2. The trajectory whisker is exactly zero in the default scene — correctly

`trajectory_spread` perturbs the axon by rotating it **about +z**, the array normal.
A single driven electrode's field **is rotationally symmetric about z**. The study's
target sits at `(0, 0, depth)` — directly on that axis. So every rotated axon traces a
congruent path through a congruent field, all K thresholds come back identical, and the
spread is **exactly 0.0**.

That is not a bug; it is the geometry. Measured live: `spread=0.000` for every
geometry. Pinned in `tests/study/test_spread.py`.

The number is honest and uninformative *here*. It measures something real only when the
cell is **off** the axis of symmetry, or the protocol drives more than the centre
electrode. The machinery (`engine/cable/trajectories.py`) is correct and tested; the
default scene is simply the one arrangement in which axon azimuth cannot matter.

**Options:** spread the *off-target* cells too (they sit off-axis, so their whiskers are
non-zero and they set `off_min_uA`, which bounds the window); or perturb a degree of
freedom the symmetry does not annihilate (axon *elevation*, or the cell's position);
or keep it target-only and state plainly that it reads zero for a centred target.

---

## 3. Array-placement sensitivity is a separate, unbuilt idea

Worth recording because it was conflated with (2) once already. "How much does the
window degrade if the array is misplaced by a few µm, or tilted?" is a *different*
question from the axon-path epistemics above — arguably a more decision-relevant one
for a lab holding this shortlist. It needs a placement-perturbation sweep axis, and
tilt is FEM-only (`engine/spec/geometry.py`). `ArrayPlacement` supports the degrees of
freedom; nothing in `engine/study/` sweeps them.
