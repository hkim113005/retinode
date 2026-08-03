"""Reproduce Retinode's headline result with one command.

The claim, in one sentence: **electrode geometry changes RGC selectivity, and only the
FEM tier can see it.** Two flat disks — 10 µm and 30 µm — score *byte-identically* on
the analytical tier (a point source, blind to an electrode's extent) and *distinctly*
on the FEM tier (which meshes the real electrode). This is the capability the whole
tool exists for, and the reason geometry studies are FEM-only.

Run it with the conda ``retinode-fem`` interpreter (the only env with DOLFINx *and*
NEURON — the FEM field and the threshold search both need it):

    FEMPY=/opt/homebrew/Caskroom/miniforge/base/envs/retinode-fem/bin/python
    $FEMPY examples/reproduce_headline.py

It reproduces the numbers recorded in docs/phase-8-findings.md and **exits non-zero if
the engine has drifted** — a real reproducibility guarantee, not just a demo. Runs a
real FEM solve + NEURON search for each diameter (~1–2 minutes).
"""

from __future__ import annotations

import sys

from app.scene import build_scene
from engine.eval import evaluate
from engine.field import AnalyticalBackend
from engine.field.fem_fenicsx import FenicsxBackend

# The recorded headline (docs/phase-8-findings.md § 1): FEM thresholds for a d10 vs d30
# flat disk on the standard target-plus-neighbour patch. The reproduction fails if the
# engine drifts outside this tolerance.
EXPECTED_FEM_uA = {10.0: 9.49, 30.0: 10.20}
TOL_uA = 0.30

_DIAMETERS = (10.0, 30.0)
_SCENE = dict(
    layout="single", pitch_um=60.0, phase_width_us=200.0, neighbor_um=40.0, sigma_S_per_m=1.0
)


def _threshold_uA(diameter_um: float, backend) -> float:  # noqa: ANN001 - a FieldBackend
    """The target's activation threshold for a flat disk of this diameter, on ``backend``."""
    scene = build_scene(electrode_um=diameter_um, **_SCENE)
    result = evaluate(scene.patch, scene.array, scene.config, scene.conductivity, backend=backend)
    if not result.activated or result.window is None:
        raise SystemExit(f"d{diameter_um:.0f} never activated the target — cannot reproduce")
    return result.window.target_uA


def _fem_backend(diameter_um: float) -> FenicsxBackend:
    # Floor the FEM domain to the cell reach (the axon of passage runs ~380 µm toward
    # the optic disc), or the solve raises on a query point outside the mesh.
    from api.study_core import _query_reach_um

    scene = build_scene(electrode_um=diameter_um, **_SCENE)
    return FenicsxBackend(min_half_width_um=_query_reach_um(scene.patch) * 1.15)


def main() -> int:
    print("Reproducing the headline: geometry changes selectivity, and only FEM sees it.")
    print("(real FEM + NEURON per diameter — a minute or two)\n")

    analytical = {d: _threshold_uA(d, AnalyticalBackend()) for d in _DIAMETERS}
    fem = {d: _threshold_uA(d, _fem_backend(d)) for d in _DIAMETERS}

    print(f"{'diameter':>10} | {'analytical':>12} | {'FEM':>10}")
    print(f"{'-' * 10}-+-{'-' * 12}-+-{'-' * 10}")
    for d in _DIAMETERS:
        print(f"{d:>8.0f} µm | {analytical[d]:>9.2f} µA | {fem[d]:>7.2f} µA")

    ok = True

    # 1. The analytical tier is a point source: the two diameters are byte-identical.
    a_lo, a_hi = analytical[10.0], analytical[30.0]
    if abs(a_lo - a_hi) < 1e-9:
        print(f"\n✓ analytical: d10 and d30 are identical ({a_lo:.2f} µA) — the point "
              "source is blind to diameter, as claimed")
    else:
        ok = False
        print(f"\n✗ analytical: expected d10 == d30 (point source), got {a_lo:.2f} vs {a_hi:.2f}")

    # 2. The FEM tier resolves the geometry: the two diameters differ.
    if abs(fem[10.0] - fem[30.0]) > TOL_uA:
        print(f"✓ FEM: d10 ({fem[10.0]:.2f} µA) and d30 ({fem[30.0]:.2f} µA) differ — "
              "the geometry effect the analytical tier can't see")
    else:
        ok = False
        print(f"✗ FEM: expected d10 and d30 to differ by > {TOL_uA} µA, "
              f"got {fem[10.0]:.2f} vs {fem[30.0]:.2f} µA")

    # 3. Provenance: the FEM numbers still match the recorded headline.
    for d, expected in EXPECTED_FEM_uA.items():
        got = fem[d]
        if abs(got - expected) <= TOL_uA:
            print(f"✓ provenance: d{d:.0f} FEM {got:.2f} µA matches the recorded {expected:.2f} µA")
        else:
            ok = False
            print(f"✗ provenance: d{d:.0f} FEM {got:.2f} µA DRIFTED from the recorded "
                  f"{expected:.2f} µA (tol ±{TOL_uA})")

    if ok:
        print("\nHEADLINE REPRODUCED ✓ — geometry changes selectivity; FEM resolves it, "
              "the analytical point source does not.")
        return 0
    print("\nREPRODUCTION FAILED ✗ — the engine has drifted from the recorded headline.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
