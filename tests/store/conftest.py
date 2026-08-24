"""Shared fixtures: real EvaluationResults built via an injected provider (no NEURON)."""

import pytest

from engine import spec
from engine.cable.population import PopulationThresholds
from engine.eval import OffTargetSet, evaluate

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
ARR = spec.ElectrodeArray(
    electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
CFG = spec.StimConfig.from_map({"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0))
# distinct scenes -> distinct result_keys (the key identifies inputs, not thresholds)
CFG_UNBOUNDED = spec.StimConfig.from_map({"e": -1.0}, waveform=spec.Waveform(phase_width_us=150.0))
CFG_INACTIVE = spec.StimConfig.from_map({"e": -1.0}, waveform=spec.Waveform(phase_width_us=100.0))
PATCH = spec.RetinalPatch(
    cells=(
        spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
        spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
    ),
    target_id="t",
    optic_disc_um=(2000.0, 0.0, -20.0),
)


def _provider(target_uA, off):
    def provider(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        return PopulationThresholds(patch.target_id, target_uA, dict(off))

    return provider


@pytest.fixture
def result_windowed():
    """Activated, off-target-limited window (finite everywhere)."""
    return evaluate(PATCH, ARR, CFG, COND, thresholds_provider=_provider(8.0, {"n1": 12.0}))


@pytest.fixture
def windowed_context():
    """The exact inputs behind result_windowed, for Project.record_run."""
    return {
        "array": ARR,
        "config": CFG,
        "patch": PATCH,
        "off_target_set": OffTargetSet(),
        "conductivity": COND,
    }


@pytest.fixture
def result_unbounded():
    """No off-targets → sow.off_min / ratio / margin are inf (exercises inf round-trip)."""
    return evaluate(PATCH, ARR, CFG_UNBOUNDED, COND, thresholds_provider=_provider(8.0, {}))


@pytest.fixture
def result_inactive():
    """Target never fired → sow / window / safety_at_target are None."""
    return evaluate(
        PATCH, ARR, CFG_INACTIVE, COND, thresholds_provider=_provider(None, {"n1": 12.0})
    )
