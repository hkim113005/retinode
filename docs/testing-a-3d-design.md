# Test runbook: putting a new 3D electrode design through Retinode

A front-to-back test procedure for a **new custom 3D electrode design**, from a cold
environment to a scored, interpreted result, with a pass/fail check at every gate. Use
it to smoke-test a build, to dogfood the tool, or to actually evaluate a design you care
about. It exercises the whole stack: the two environments, the API, the React app, the
FEM dispatch, the overlap policy, the 3D loupe, CAD upload, and the code path.

The running example is a **5 µm-radius, 30 µm-tall tip-only pillar** against a flat disk
of the same footprint. Swap in your own dimensions anywhere.

Legend: **DO** = the action · **EXPECT** = what you should see · **PASS/FAIL** = the gate.

---

## Stage 0: environments (once per machine)

1. **uv env** (analytical + NEURON + API).
   - DO: `uv sync --extra cable --extra api --extra dev --extra store` then
     `(cd engine/cable/mechanisms && uv run nrnivmodl .)`
   - EXPECT: sync completes; `nrnivmodl` prints "Successfully created arm64/special"
     (or `x86_64/special` on an Intel Mac).
   - PASS: `uv run --extra cable python -c "import neuron; print('neuron ok')"` prints
     `neuron ok`.

   > **If `nrnivmodl` fails** with `FileNotFoundError: .../Applications/NEURON/...` or
   > `No rule to make target '/var/folders/.../wheel/platlib/bin/nrnmech_makefile'`, the
   > `neuron` wheel is mis-installed. The `.venv/bin/nrnivmodl` wrapper points at a
   > separately-installed system NEURON, and the wheel baked in its *build-time temp
   > prefix* instead of its install path. `import neuron` still works; only the compile
   > tooling is broken. Fix it by repointing the prefix in the two **text** build files
   > (never the `.dylib`/`.a` binaries), then compiling with the real binary:
   >
   > ```bash
   > DATA="$PWD/.venv/lib/python3.12/site-packages/neuron/.data"
   > TMP=$(grep -oE '/var/folders/[^"'"'"' ]*/wheel/platlib' "$DATA/bin/nrnivmodl" | head -1)
   > perl -pi -e "s|\Q$TMP\E|$DATA|g" "$DATA/bin/nrnivmodl" "$DATA/include/nrnconf.h"
   > (cd engine/cable/mechanisms && uv run --extra cable "$DATA/bin/nrnivmodl" .)
   > ```
   >
   > This patches `.venv/`, which is **not** version-controlled, so a `uv sync` that
   > reinstalls `neuron` undoes it. The durable fix is a `neuron` build whose wheel
   > relocates properly.

   > **Always invoke pytest as `uv run ... python -m pytest`.** A bare `pytest` may
   > resolve to a conda base Python and fail on `datetime.UTC`, which needs 3.11+.

2. **conda FEM env** (DOLFINx + gmsh + NEURON, needed for anything 3D).
   - DO: `conda env create -f env/fem-environment.yml`
   - PASS: `FEMPY=/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python`
     then `$FEMPY -c "import dolfinx, gmsh, neuron; print('fem env ok')"` prints
     `fem env ok`. If your env lives elsewhere, `export RETINODE_FEM_PYTHON=...` and
     point `FEMPY` at the same interpreter.

> If Stage 0.2 fails you can still do the analytical and flat-disk parts, but every 3D
> step will stop with "the FEM env is not available". That refusal is itself a correct
> behaviour worth verifying (Stage 6).

---

## Stage 1: back-end smoke test (no UI, about 2 min)

The fastest proof the engine scores your geometry, before you touch the browser.

3. **Score the design in code.**
   - DO: edit `examples/custom_3d_electrode.py` to your dimensions (the `custom_pillar()`
     body), then `$FEMPY examples/custom_3d_electrode.py`
   - EXPECT: a flat disk and your pillar both score, and the pillar's `target threshold`
     and `selective window` differ from the disk's.
   - PASS: both print a `target threshold` and `selective window`; the pillar under the
     `reject` policy is refused because it penetrates the cell, then scores under
     `displace`.

4. **Reproduce the headline (regression gate).**
   - DO: `$FEMPY examples/reproduce_headline.py`
   - EXPECT: d10 and d30 identical on analytical (8.31 µA), distinct on FEM (9.49 vs
     10.20 µA).
   - PASS: it ends with `HEADLINE REPRODUCED ✓` and exit code 0. A non-zero exit means
     the engine has drifted, so stop and investigate before trusting any number.

---

## Stage 2: launch the app

5. **Start the API** (uv env).
   - DO: `uv run --extra api --extra cable uvicorn api.main:create_app --factory --port 8000`
   - PASS: `curl -s http://localhost:8000/health` returns `{"status":"ok"}`.

6. **Start the web client** (second terminal).
   - DO: `npm --prefix app/web install` (first time) then `npm --prefix app/web run dev`
   - DO: open **http://localhost:5173**.
   - PASS: the Compare screen loads with a blue field heatmap and an "Analytical" tier chip.

---

## Stage 3: baseline (flat disk)

7. **Establish the flat-disk baseline.**
   - DO: leave **Electrode body = Flat**; set the electrode diameter to your footprint.
   - EXPECT: a live analytical field (contours labelled in mV), the target filled and the
     neighbour open, a 3D loupe in the corner.
   - DO: click **Run scorecard**, wait for the job.
   - EXPECT: an operating window, meaning a target threshold, a selective window, and the
     off-target thresholds.
   - PASS: you have a baseline threshold and window to compare the 3D design against. Note
     them down.

---

## Stage 4: author the 3D design (the core test)

8. **Switch to your 3D body.**
   - DO: in the rail, **Electrode body → Pillar** (or Dome / Taper). Set **Radius**,
     **Height**, and **Conductive faces** (tip / sides / all).
   - EXPECT (the honest-preview behaviour):
     - the heading reads e.g. **"Monopolar · Pillar electrode"**;
     - the tier chip flips to **"3D · FEM required"**;
     - the live 2D field is **replaced** by a panel: *"the analytical preview is a point
       source and can't represent electrode geometry"*;
     - the button relabels to **"Run field (FEM)"**.
   - PASS: the analytical heatmap is GONE, because a body must not show a misleading flat
     field. **FAIL** if a 2D field still renders for a bodied electrode.

9. **Solve the real bodied field.**
   - DO: click **Run field (FEM)**. Wait 30 to 60 s for a real conda FEM solve.
   - EXPECT: the tier chip becomes **"FEM ✓ inked"**, and a real heatmap renders **with a
     hole** at the axis where the metal occupies the cell plane (a penetrating body).
   - PASS: the FEM field draws and shows the hole. A flat disk never has a hole; a 30 µm
     pillar does.

10. **Score the 3D design.**
    - DO: click **Run scorecard**, which dispatches to the conda env for a body.
    - EXPECT: an operating window for the 3D design, with a target threshold, a selective
      window, and a limiting factor (off-target vs charge ceiling).
    - PASS: a window comes back, and its numbers **differ from the flat baseline**
      (Stage 3). That difference is the geometry effect, the reason the tool exists.

11. **Inspect the 3D form.**
    - DO: click **Expand the 3D array view** (the loupe, corner).
    - EXPECT: the true solid, a pillar / dome / taper protruding into the tissue slab,
      with the cells at depth. The caption names what was drawn, for example
      `Array · 3D · pillar r5 × 30`.
    - PASS: the body renders as a 3D solid, not a flat disk. (In a headless or preview
      browser the WebGL canvas may not paint; check in a real browser if so. The caption
      still tells you what the loupe was handed.)

---

## Stage 5: overlap policy (penetrating designs)

12. **reject vs displace.** A body taller than the roughly 20 µm cell plane hits a cell.
    - DO: with a tall pillar, set **Cell overlap = reject**, click **Run scorecard**.
    - EXPECT: the job **errors** with an `OverlapConflict`, because a cell is embedded in
      metal.
    - PASS: it refuses rather than returning a silently-wrong score.
    - DO: switch **Cell overlap = displace**, re-run.
    - EXPECT: it scores, with the in-metal compartments severed.
    - PASS: reject refuses, displace scores. (A short body that stays above the cell plane
      scores under either.)

---

## Stage 6: CAD upload (optional)

13. **Upload a solid.**
    - DO: **Electrode body → CAD**, pick a `.step` / `.stp` / `.brep` file.
    - EXPECT: the filename comes back next to the picker; the body becomes your CAD solid;
      Run field and Run scorecard work as in Stage 4.
    - EXPECT: with the FEM env present, the solid is measured at upload time (a short
      subprocess, well under a second for a small pillar) and the loupe immediately draws
      its **bounding cylinder**, captioned along the lines of `Array · 3D · CAD r5 × 30`.
      Without the FEM env the upload still succeeds and the loupe's caption says the CAD
      solid's shape needs FEM, rather than drawing a flat disk it cannot vouch for.
    - PASS: a STEP or BREP is accepted, and an **`.stl` is rejected** with "unsupported CAD
      format '.stl'; use STEP or BREP (STL is a surface mesh, not a solid, and can't be cut
      cleanly)". The file picker filters to `.step,.stp,.brep`, so you have to choose "all
      files" in the OS dialog to test the rejection.

14. **Check the unit handling.** A STEP declares its own length unit, and CAD packages
    export millimetres by default.
    - DO: upload a solid authored at true micron scale in a millimetre STEP, for example a
      5 x 30 body.
    - EXPECT: the declared unit is honoured, so 5 x 30 mm becomes 5000 x 30000 µm, which
      is far larger than a retinal electrode.
    - PASS: the load is **refused** with a message naming the converted size and the
      2000 µm cap, rather than solving something physically meaningless. (A BREP declares
      no unit, so its numbers are read as microns; there is nothing to check there.)

---

## Stage 7: compare, decide, export

15. **Side-by-side.** Each scored run is remembered.
    - DO: score the flat baseline and the 3D design, then read them in the run history.
    - EXPECT: two runs with distinct windows. The app **refuses to compare** two runs
      measured against different off-target sets, flagging the category error instead of
      producing a silently bad diff.
    - PASS: you can state, in one line, how your 3D design's window compares to the disk's.

16. **Shortlist (if you swept several).** Study → sweep diameters × pitches → Candidates.
    - PASS: Candidates gives a ranked, charge-safe shortlist you can export with **Export
      list (JSON)** or **Export table (CSV)**.

---

## Stage 8: teardown

17. Stop the dev servers (Ctrl-C in both terminals). Nothing persists server-side; the run
    history lives in the browser only. Uploaded CAD solids sit in a temp-dir cache
    (`RETINODE_CAD_DIR`), which is a cache, not a system of record.

---

## Fast pass/fail summary

| Gate | Pass condition |
|---|---|
| Env | `neuron ok` (uv) and `fem env ok` (conda) |
| Back-end | the example scores; `reproduce_headline.py` prints `HEADLINE REPRODUCED ✓`, exit 0 |
| App up | `/health` ok; Compare loads |
| Honest preview | a body hides the 2D analytical field and shows "3D · FEM required" |
| FEM field | "FEM ✓ inked" heatmap with the metal hole |
| Scorecard | a window that differs from the flat baseline |
| Overlap | reject refuses a penetrating body; displace scores |
| CAD | STEP/BREP accepted; STL rejected; a millimetre solid refused on the size cap |

## If a step fails

See the troubleshooting table in [user-guide.md](user-guide.md#troubleshooting). The
common causes: the FEM env is missing ("the FEM env is not available"), a FEM script was
run in the uv interpreter (`ModuleNotFoundError: dolfinx`), the NEURON mechanisms are not
compiled, or a shaped electrode reads identical to a flat one. That last one means you are
on the analytical tier; the UI should force FEM for a body, and if it doesn't, that is the
bug.
