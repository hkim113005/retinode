"""Test a custom 3D electrode shape end to end.

Run this with the conda **retinode-fem** interpreter (the only env with DOLFINx
*and* NEURON) — shaped/3D electrodes are FEM-only, because the analytical tier is a
point source that cannot see an electrode's extent at all:

    FEMPY=/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python
    $FEMPY examples/custom_3d_electrode.py

The Compare screen can also author a body (Flat/Dome/Pillar/Taper + CAD upload) and
run it on FEM — see docs/custom-electrode.md. This script is the code path: for
scripting, reproducibility, sweeps, and anything the rail doesn't expose.

What it does: scores a flat 10 µm disk and a custom 5 µm-radius, 30 µm-tall pillar
(tip-only injection) against the *same* target-plus-bystander patch, both on the FEM
field tier, and prints the operating window for each. The two differ because the
pillar concentrates its injection deep in the tissue — exactly the effect a point
source misses.
"""

from __future__ import annotations

from app.scene import build_patch
from engine.eval import evaluate
from engine.eval.overlap import OverlapConflict
from engine.field.fem_fenicsx import FenicsxBackend
from engine.spec import (
    Cylinder,
    Electrode,
    ElectrodeArray,
    HomogeneousConductivity,
    StimConfig,
    Waveform,
)


def score(array: ElectrodeArray, label: str, *, overlap_policy: str = "reject") -> None:
    """Score one array on the FEM tier and print its operating window."""
    patch = build_patch(neighbor_um=40.0)
    config = StimConfig.from_map({"e0": -1.0}, waveform=Waveform(phase_width_us=200.0))
    sigma = HomogeneousConductivity(sigma_S_per_m=1.0)

    # The FEM domain must contain every point the field is sampled at — the cell's
    # compartments, whose axon of passage reaches ~380 µm toward the optic disc, far
    # outside a mesh sized for the electrode. Floor it, or the solve raises on a point
    # outside the domain. (This is the fix behind the Study screen's FEM path.)
    backend = FenicsxBackend(min_half_width_um=450.0)

    result = evaluate(patch, array, config, sigma, backend=backend, overlap_policy=overlap_policy)

    print(f"\n=== {label} ===")
    if not result.activated or result.window is None:
        print("  target never fired in the searched range — no operating window")
        return
    w = result.window
    print(f"  target threshold : {w.target_uA:.2f} µA")
    print(f"  selective window : {w.usable_margin_uA:.2f} µA  (limited by {w.limiting})")
    print(f"  charge ceiling   : {w.safety_ceiling_uA:.2f} µA")
    print(f"  off-target thresholds: "
          f"{ {k: round(v, 2) for k, v in result.thresholds.off_target_thresholds_uA.items()} }")


def flat_disk() -> ElectrodeArray:
    """The baseline: a plain 10 µm flat disk on the array plane (body=None)."""
    e = Electrode(id="e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0)
    return ElectrodeArray(electrodes=(e,))


def custom_pillar() -> ElectrodeArray:
    """The custom 3D shape: a 5 µm-radius pillar reaching 30 µm into the tissue,
    injecting only from its deep tip cap (conductive_faces="tip"). Swap in
    ``Frustum(base_radius_um=..., top_radius_um=..., height_um=...)`` for a taper, or
    ``Hemisphere(radius_um=...)`` for a dome — or load a CAD solid, see below."""
    e = Electrode(
        id="e0",
        pos_um=(0.0, 0.0, 0.0),
        shape="disk",
        size_um=10.0,
        body=Cylinder(radius_um=5.0, height_um=30.0, conductive_faces="tip"),
    )
    return ElectrodeArray(electrodes=(e,))


# --- A CAD shape instead of a primitive (uncomment, point at a real STEP/BREP) -----
#
# from engine.field.mesh3d import load_cad_body
# body = load_cad_body("my_electrode.step", conductive_faces="tip")  # gmsh reads it
# cad_e = Electrode(id="e0", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=0.0, body=body)
# score(ElectrodeArray(electrodes=(cad_e,)), "CAD electrode")


if __name__ == "__main__":
    print("Scoring a flat disk vs a custom 3D pillar on the FEM tier "
          "(this runs real FEM + NEURON — a minute or two)...")

    # The flat disk sits on the array plane and overlaps nothing.
    score(flat_disk(), "flat 10 µm disk")

    # The 30 µm-tall pillar PENETRATES: the target soma sits at ~20 µm depth, so two of
    # its compartments end up inside the metal. This is a real design constraint, and
    # the overlap policy is how you handle it:
    #   - "reject" refuses to score a cell embedded in an electrode (safe default);
    #   - "displace" severs the in-metal compartments (models a penetrating electrode
    #     that displaced that tissue) and scores the rest.
    try:
        score(custom_pillar(), "pillar · reject policy", overlap_policy="reject")
    except OverlapConflict as e:
        print("\n=== pillar · reject policy ===")
        print(f"  refused (as designed): {e}")

    score(custom_pillar(), "pillar · displace policy", overlap_policy="displace")

    print("\nThe pillar's window differs from the disk's because it concentrates "
          "injection deep in the tissue — the geometry effect the analytical point "
          "source cannot see. And a penetrating design forces the overlap decision.")
