# How to test a custom electrode shape

A task-oriented walkthrough. Take an electrode geometry you care about, whether a
shaped 2D face, a penetrating pillar, or an imported CAD solid, and get a real
selectivity scorecard for it against a target neuron and its bystander. It is the
practical companion to the geometry reference in
[electrode-geometry.md](electrode-geometry.md): read that for the full domain model,
and this for "just run it."

The runnable version of everything below is
[`examples/custom_3d_electrode.py`](../examples/custom_3d_electrode.py). Copy it and
edit the electrode.

## TL;DR

```bash
# shaped/3D electrodes are FEM-only; run in the conda env that has DOLFINx *and* NEURON
/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python examples/custom_3d_electrode.py
```

```
=== flat 10 µm disk ===
  target threshold : 9.49 µA
  selective window : 4.75 µA  (limited by off_target)
  charge ceiling   : 24.92 µA
  off-target thresholds: {'neighbor': 14.24}

=== pillar · displace policy ===
  target threshold : 7.83 µA
  selective window : 6.05 µA  (limited by off_target)
  charge ceiling   : 24.92 µA
  off-target thresholds: {'neighbor': 13.88}
```

The pillar wins on both axes here, with a lower target threshold *and* a wider
selective window, because its deep, tip-only injection concentrates current where a
flat disk spreads it. That difference is the whole point: it is the geometry effect
the analytical tier is structurally blind to.

## In the UI, or in code

There are two ways to test a custom shape:

- **In the Compare screen** (the quick path). The control rail has an **Electrode
  body** selector (Flat / Dome / Pillar / Taper, plus a **CAD** file picker for a
  STEP or BREP solid) with dimension inputs, a conductive-faces selector
  (tip/sides/all), and a Cell overlap policy (reject/displace). Author a body and the
  live 2D field is replaced by a "3D · FEM required" prompt, because the analytical
  preview cannot represent geometry. **Run field (FEM)** and **Run scorecard** then
  dispatch to the conda env and return the real potential (with a hole where the metal
  sits) and the operating window. The true solid also renders in the 3D loupe.
- **In code** (this how-to). Scripting, reproducibility, parameter sweeps, and
  anything the rail doesn't expose (array tilt, bipolar bodies, a custom patch) still
  live here. The rest of this document is the code path.

## Two things to know before you start

1. **Custom shapes are FEM-only, so use the conda env.** The analytical field tier is
   a point source: it sees only `pos_um` and is blind to an electrode's diameter,
   height, and shape, so two different diameters produce byte-identical fields.
   Anything where the geometry is the variable *must* be solved with FEM, and the only
   interpreter with DOLFINx **and** NEURON is the conda `retinode-fem` env. The `uv`
   env cannot run this. If `import dolfinx` fails, you're in the wrong interpreter.
   (The UI handles this for you: a bodied electrode dispatches to the conda env.)

2. **The FEM domain must contain the whole cell.** The cell's axon of passage reaches
   about 380 µm toward the optic disc, far outside a mesh sized for the electrode. If
   the auto-sized domain is too tight, the solve raises on a query point outside the
   mesh. Floor it with `FenicsxBackend(min_half_width_um=450.0)`. The example does
   this, and it is the same fix behind the Study screen's FEM path.

## Walkthrough

### 1. Build the tissue patch

A "patch" is the scored scene: one **target** cell plus its **bystanders**, with an
optic-disc direction that sets axon trajectories. `build_patch(neighbor_um=40.0)`
puts one neighbor 40 µm away. Selectivity is the target firing while that neighbor
stays silent.

```python
from app.scene import build_patch
patch = build_patch(neighbor_um=40.0)
```

### 2. Describe the electrode

A plain flat disk is the baseline (`body=None`):

```python
from engine.spec import Electrode, ElectrodeArray
flat = Electrode(id="e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)
disk_array = ElectrodeArray(electrodes=(flat,))
```

A 3D body makes it a solid protruding into the tissue. Here, a 5 µm-radius pillar
reaching 30 µm deep, injecting **only from its tip cap**:

```python
from engine.spec import Cylinder
pillar = Electrode(
    id="e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0,
    body=Cylinder(radius_um=5.0, height_um=30.0, conductive_faces="tip"),
)
pillar_array = ElectrodeArray(electrodes=(pillar,))
```

Swap the body for any other shape and the rest of the script is unchanged:

| Want | Use |
|---|---|
| A dome | `Hemisphere(radius_um=10)` |
| A straight pillar | `Cylinder(radius_um=5, height_um=30, conductive_faces="tip")` |
| A tapered tip | `Frustum(base_radius_um=8, top_radius_um=2, height_um=20)` |
| Your own CAD solid | `load_cad_body("my_electrode.step", conductive_faces="tip")` |

`conductive_faces` is one of `"tip"`, `"sides"`, or `"all"`, and selects which
surfaces inject current. A hemisphere takes no selector because its whole curved
surface conducts. CAD accepts **STEP and BREP** solids, not STL. See
[electrode-geometry.md](electrode-geometry.md) for the full menu.

**CAD units.** A STEP file declares its own length unit, and CAD packages export
millimetres by default, so `load_cad_body` reads that declaration and converts to
microns. A solid drawn as "5 x 30" in a millimetre STEP therefore loads as
5000 x 30000 µm, which exceeds the plausibility cap and is refused with an
explanation rather than silently solved. A BREP declares no unit (it is a raw
geometry dump), so its numbers are taken as microns; that is the format's own
limitation, not a guess the loader can improve on.

### 3. Score it on the FEM tier

```python
from engine.eval import evaluate
from engine.field.fem_fenicsx import FenicsxBackend
from engine.spec import HomogeneousConductivity, StimConfig, Waveform

config = StimConfig.from_map({"e0": -1.0}, waveform=Waveform(phase_width_us=200.0))
sigma = HomogeneousConductivity(sigma_S_per_m=1.0)
backend = FenicsxBackend(min_half_width_um=450.0)   # floor the domain (see note 2 above)

result = evaluate(patch, disk_array, config, sigma, backend=backend)
```

`evaluate` meshes the geometry, solves the extracellular field, then runs the NEURON
threshold search for the target and every bystander. `result.window` holds the
operating window; `result.thresholds.off_target_thresholds_uA` is the per-bystander
threshold map.

### 4. Handle penetration: the overlap policy

The 30 µm pillar reaches deeper than the target soma (which sits at about 20 µm), so
two of the target's compartments end up **inside the metal**. That is a physical
conflict, and `evaluate` makes you decide what it means via `overlap_policy`:

- **`"reject"`** (default) refuses to score a cell embedded in an electrode and raises
  `OverlapConflict`. Usually the right answer, because for an epiretinal design a
  penetrating electrode hitting a cell is a red flag, not a feature.
- **`"displace"`** models the electrode having displaced that tissue: it **severs** the
  in-metal compartments, never querying the field there and never detecting a spike
  there, and scores the cell on its survivors. The NEURON model is unchanged; only
  which compartments are driven and monitored changes.

The example demonstrates both. It catches the `reject` refusal and then re-scores with
`displace`:

```python
from engine.eval.overlap import OverlapConflict
try:
    evaluate(patch, pillar_array, config, sigma, backend=backend, overlap_policy="reject")
except OverlapConflict as e:
    print(f"refused (as designed): {e}")

result = evaluate(patch, pillar_array, config, sigma, backend=backend, overlap_policy="displace")
```

A shorter body that stays below the cell plane (say `height_um=15`) overlaps nothing
and scores under the default `reject` with no ceremony. Reach for `displace` only when
penetration is intentional.

### 5. Read the scorecard

```python
w = result.window
print(f"target threshold : {w.target_uA:.2f} µA")           # amplitude that fires the target
print(f"selective window : {w.usable_margin_uA:.2f} µA  ({w.limiting})")  # headroom before a bystander fires or charge caps
print(f"charge ceiling   : {w.safety_ceiling_uA:.2f} µA")   # charge-density safety limit
print(result.thresholds.off_target_thresholds_uA)           # {'neighbor': 14.24}
```

- **target threshold**: the smallest amplitude that makes the target spike. Lower is
  easier to drive.
- **selective window**: the usable headroom, meaning how much you can turn the
  amplitude up above target-threshold before you either make a **bystander** fire
  (`limiting = "off_target"`) or hit the **charge-density ceiling** (`limiting =
  "safety"`). Bigger is a more selective electrode.
- **charge ceiling**: the amplitude at which charge density crosses the safety limit.
- **off-target thresholds**: the threshold of each bystander, so you can see *which*
  neighbor is the binding constraint.

If `result.activated` is `False` (or `result.window is None`), the target never fired
in the searched range, so there is no operating window to report.

## Adapting it to your question

- **A different target/bystander layout**: change `build_patch(neighbor_um=...)`, or
  build a custom patch (see [electrode-geometry.md](electrode-geometry.md) and
  `app/scene.py`).
- **A different waveform**: `Waveform(phase_width_us=..., cathodic_first=...)`. Note
  that the threshold search defaults to monophasic. `cathodic_first` only bites for
  biphasic pulses, where it changes the spike **initiation site** (soma vs AIS), not
  the threshold amplitude.
- **Layered tissue**: swap `HomogeneousConductivity` for a layered conductivity, which
  the FEM backend honors; see the validation docs.
- **A whole family of shapes at once**: don't loop `evaluate` by hand, use a geometry
  sweep. `pillar_geometry_grid(diameters_um=..., pitches_um=..., heights_um=...)`
  builds the arrays and `geometry_sweep` scores them to a Pareto frontier, routing to
  FEM automatically. See [electrode-geometry.md](electrode-geometry.md) § "Sweeping 3D
  designs."

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: dolfinx` | Running in the `uv` env | Use the conda `retinode-fem` interpreter |
| `OverlapConflict: cell ... inside an electrode body` | A 3D body contains cell compartments | Intentional? use `overlap_policy="displace"`. Not? shorten or move the body |
| Solve raises on a point outside the domain | Auto-sized mesh too tight for the axon of passage | Raise `FenicsxBackend(min_half_width_um=...)` |
| Disk and shaped electrode give identical numbers | You're on the analytical tier (point source) | Pass a `FenicsxBackend`; the analytical tier can't see geometry |
| A CAD solid is refused as far larger than a retinal electrode | Its declared length unit is millimetres, or a BREP was authored in mm | Re-export at micron scale, or scale the geometry down before loading |
| `CadBody` overlap seems too coarse | Bounding-cylinder fallback (no baked triangulation) | Load via `load_cad_body`, which bakes the surface for an exact check |

## Why this is trustworthy (and where it isn't)

The FEM field is validated against a closed form (the hemisphere reproduces the
point-source law), for mesh convergence, and across two independent solvers (DOLFINx
and NGSolve agree to a few percent). What geometry raises is **field and placement**
fidelity, not physiological fidelity. The biophysics caveats are unchanged: a mouse
RGC morphology, and trend-not-magnitude validation. This is a hypothesis tester for
electrode **designs**, not an absolute predictor of clinical thresholds. Treat the
*comparison* between two geometries as the signal, not either absolute number.
