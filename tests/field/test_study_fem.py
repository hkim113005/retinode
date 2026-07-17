"""P8 S4: the geometry study on the real FEM tier, with real NEURON.

Lives in tests/field so the conda ``test-fem`` CI job (DOLFINx + gmsh + NEURON)
collects it. This is the payoff of forcing FEM on geometry sweeps: unlike the
analytical point source, FEM resolves the electrode surface, so two diameters
produce *different* thresholds — the sweep can finally tell them apart.
"""

import pytest

pytest.importorskip("dolfinx")
pytest.importorskip("neuron")

from api.study_core import run_study  # noqa: E402


@pytest.mark.fem
@pytest.mark.slow
def test_fem_study_distinguishes_two_diameters():
    """The whole reason for the FEM dispatch: on the analytical tier these two
    diameters give a byte-identical field and the same threshold; on FEM they must
    differ."""
    controls = {
        "diameters_um": [10.0, 30.0],  # a 3x diameter gap — the effect should be clear
        "pitches_um": [60.0],
        "arrangement": "hex",
        "aperture_um": 0.0,  # a single electrode: fastest mesh, and pitch is moot
        "neighbor_um": 40.0,
        "sigma_S_per_m": 1.0,
    }
    result = run_study(controls)  # no provider, no backend -> forces FEM + real NEURON

    assert result["n_geometries"] == 2
    by_d = {p["diameter_um"]: p for p in result["points"] if p["cost_uA"] is not None}
    assert set(by_d) == {10.0, 30.0}, "both geometries should have fired"

    t10, t30 = by_d[10.0]["cost_uA"], by_d[30.0]["cost_uA"]
    # the fields genuinely differ, so the thresholds do too — the flat-frontier bug
    # is gone. (On the analytical tier these were byte-identical.)
    assert abs(t10 - t30) > 1e-3, f"FEM should separate the diameters: {t10} vs {t30}"
