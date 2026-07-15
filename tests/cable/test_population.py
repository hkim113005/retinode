"""S6c: per-cell population thresholds over a RetinalPatch (NEURON-marked).

Convention: array/electrodes on the boundary at z=0, cells in tissue below (z<0).
"""

import pytest

from engine import spec
from engine.cable.population import population_thresholds

pytestmark = pytest.mark.neuron

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)


def _patch():
    return spec.RetinalPatch(
        cells=(
            spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
            spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),  # in radius
            spec.RGC(
                id="far", cell_type="parasol_on", soma_um=(500.0, 0.0, -20.0)
            ),  # out of radius
        ),
        target_id="t",
        optic_disc_um=(2000.0, 0.0, -20.0),
    )


def test_population_thresholds(neuron_h):
    patch = _patch()
    array = spec.ElectrodeArray(
        electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
    )
    config = spec.StimConfig.from_map(
        {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0), distant_return=True
    )
    r = population_thresholds(patch, array, config, COND)

    assert r.target_id == "t"
    assert r.target_threshold_uA is not None and 1.0 < r.target_threshold_uA < 100.0
    # n1 is within the off-target soma radius; far (500 um) is not selected
    assert "n1" in r.off_target_thresholds_uA
    assert "far" not in r.off_target_thresholds_uA
    # the target sits under the electrode, so it is the most excitable
    assert all(r.target_threshold_uA < v for v in r.off_target_thresholds_uA.values())
