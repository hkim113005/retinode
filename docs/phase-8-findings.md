# Phase 8 findings

Closing Phase 7's deferrals surfaced two limits bigger than the deferrals themselves.
Both are **pinned by tests** so they cannot be quietly forgotten again.

---

## 1. The analytical tier is blind to electrode geometry, so the Study sweep is flat

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
selectivity-versus-cost frontier**. On the analytical tier, which was the default and
the tier Candidates stamped on every exported row, every point collapses onto the same
coordinates. A real two-geometry run returns `threshold=8.31, window=4.51` for **both**
d10 and d20. The frontier is flat by construction, and the ranking it feeds is ranking
noise.

*This was invisible during Phase 7 because every live verification of Study used a
**fake thresholds provider** whose invented cost depended on diameter. The fake had a
geometry dependence the real engine does not.*

`docs/electrode-geometry.md` already says shaped and 3D electrodes are FEM-only and
that "the analytical tier is a point source". What nobody joined up: **that makes the
entire geometry-sweep premise FEM-only too.** `resolve_field_tier`
(`engine/study/geometry_sweep.py`) picks a tier from the **conductivity alone**:
homogeneous means analytical, "exact for a half-space". It is exact for a *point
source* in a half-space. It has no notion that the electrode's own geometry might
demand FEM.

**Options were weighed:** disk model, honest badge, force-FEM. The disk model would
restore a cheap tier that sees diameter (Newman's oblate-spheroidal solution gives a
~9% Ve spread across the sweep, in the correct direction), but it still cannot see
pitch or shaped and 3D electrodes. Those are irreducibly FEM.

**Resolved (P8 S4): force FEM for geometry sweeps.** The engine now knows the
analytical tier is diameter-blind. `geometry_field_tier` and
`require_geometry_distinguishable` turn a diameter sweep on the analytical tier into a
*raised error* rather than a flat frontier, and the Study route dispatches the whole
sweep to the conda `retinode-fem` env (FEM field plus real NEURON), mirroring the FEM
field dispatch. **Verified end-to-end:** a 2-diameter study returns 9.49 µA (d10)
against 10.20 µA (d30), byte-identical on the analytical tier and distinct on FEM.

The cost is real and now stated in the UI: ~28 s per geometry, so a 4×4 sweep takes
about 8 min, against seconds for the old flat frontier. That is the price of the FEM
tier the question actually requires. The live run also forced a genuine engine fix:
the FEM domain must be floored to the cell's query reach, because the axon of passage
reaches 378 µm toward the optic disc, far outside a domain sized for a small
electrode, and the solve crashes on a point outside the mesh.

---

## 2. The trajectory whisker is exactly zero in the default scene, correctly

`trajectory_spread` perturbs the axon by rotating it **about +z**, the array normal.
A single driven electrode's field **is rotationally symmetric about z**, and the
study's target sits at `(0, 0, depth)`, directly on that axis. So every rotated axon
traces a congruent path through a congruent field, all K thresholds come back
identical, and the spread is **exactly 0.0**.

That is not a bug; it is the geometry. Measured live: `spread=0.000` for every
geometry. Pinned in `tests/study/test_spread.py`.

The number is honest and uninformative *here*. It measures something real only when the
cell is **off** the axis of symmetry, or the protocol drives more than the centre
electrode. The machinery (`engine/cable/trajectories.py`) is correct and tested; the
default scene is simply the one arrangement in which axon azimuth cannot matter.

**Options.** Spread the *off-target* cells too, since they sit off-axis, so their
whiskers are non-zero and they set `off_min_uA`, which bounds the window. Or perturb a
degree of freedom the symmetry does not annihilate: axon *elevation*, or the cell's
position. Or keep it target-only and state plainly that it reads zero for a centred
target.

---

## 3. Array-placement sensitivity is a separate, unbuilt idea

Worth recording because it was conflated with (2) once already. "How much does the
window degrade if the array is misplaced by a few µm, or tilted?" is a *different*
question from the axon-path epistemics above, and arguably a more decision-relevant one
for a lab holding this shortlist. It needs a placement-perturbation sweep axis, and
tilt is FEM-only (`engine/spec/geometry.py`). `ArrayPlacement` supports the degrees of
freedom; nothing in `engine/study/` sweeps them.
