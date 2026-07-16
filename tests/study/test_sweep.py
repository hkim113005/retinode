"""P2 S4: configuration sweeps — generators, caching, provenance, and ranking."""

import pytest

from engine import spec
from engine.cable.population import PopulationThresholds
from engine.eval import evaluate
from engine.field import AnalyticalBackend
from engine.store.project import Project
from engine.study.sweep import (
    pareto_selectivity_safety,
    rank_by_window,
    steering_sweep,
    sweep,
    waveform_shape_sweep,
)

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
ARR = spec.ElectrodeArray(
    electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
CFG = spec.StimConfig.from_map({"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0))
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


def _result(target_uA, off, config=CFG):
    return evaluate(PATCH, ARR, config, COND, thresholds_provider=_provider(target_uA, off))


# --- configuration generators (pure) ----------------------------------------


def test_waveform_shape_sweep_varies_only_the_phase_width():
    cfgs = waveform_shape_sweep({"e": -1.0}, [100.0, 200.0, 300.0])
    assert [c.waveform.phase_width_us for c in cfgs] == [100.0, 200.0, 300.0]
    assert all(c.weight_map() == {"e": -1.0} for c in cfgs)


def test_steering_sweep_varies_only_the_weight_pattern():
    maps = [{"a": -1.0, "b": 0.0}, {"a": -0.5, "b": -0.5}]
    cfgs = steering_sweep(maps, phase_width_us=150.0)
    assert all(c.waveform.phase_width_us == 150.0 for c in cfgs)
    assert [c.weight_map() for c in cfgs] == maps


# --- sweep orchestration: collect, cache, record (injected provider) --------


def test_sweep_evaluates_stores_and_records_provenance(tmp_path):
    configs = waveform_shape_sweep({"e": -1.0}, [100.0, 150.0, 200.0])
    store = Project.open(tmp_path / "proj")
    r = sweep(
        ARR, PATCH, COND, configs, store=store, thresholds_provider=_provider(8.0, {"n1": 12.0})
    )
    assert r.n_evaluated == 3 and r.n_cached == 0
    for res in r.results:
        assert store.get_result(res.result_key) == res  # stored
        assert store.provenance.find(res.result_key) is not None  # and traceable


def test_sweep_serves_cached_results_and_skips_re_evaluation(tmp_path):
    configs = waveform_shape_sweep({"e": -1.0}, [100.0, 150.0])
    store = Project.open(tmp_path / "proj")
    calls: list[float] = []

    def counting(patch, array, config, conductivity, *, off_target_set=None, backend=None, **_):
        calls.append(config.waveform.phase_width_us)
        return PopulationThresholds(patch.target_id, 8.0, {"n1": 12.0})

    first = sweep(ARR, PATCH, COND, configs, store=store, thresholds_provider=counting)
    assert first.n_evaluated == 2 and len(calls) == 2

    calls.clear()
    second = sweep(ARR, PATCH, COND, configs, store=store, thresholds_provider=counting)
    assert second.n_cached == 2 and second.n_evaluated == 0
    assert calls == []  # nothing re-evaluated — all served from the store
    assert {r.result_key for r in second.results} == {r.result_key for r in first.results}


def test_sweep_without_a_store_just_collects():
    configs = waveform_shape_sweep({"e": -1.0}, [100.0, 200.0])
    r = sweep(ARR, PATCH, COND, configs, thresholds_provider=_provider(8.0, {"n1": 12.0}))
    assert len(r.results) == 2 and r.n_cached == 0


# --- ranking a shortlist ----------------------------------------------------


def test_rank_by_window_orders_by_margin_then_ratio():
    # ceiling ~24.9 uA for this array+waveform, so off=40 is safety-limited.
    a = _result(8.0, {"n1": 20.0})  # off-limited: margin 12, ratio 2.5
    b = _result(8.0, {"n1": 12.0})  # off-limited: margin 4,  ratio 1.5
    c = _result(8.0, {"n1": 40.0})  # safety-limited: margin ~16.9 (widest)
    assert rank_by_window([b, c, a]) == [c, a, b]


def test_rank_puts_unusable_windows_last():
    good = _result(8.0, {"n1": 20.0})  # usable
    bad = _result(30.0, {"n1": 40.0})  # target above the safety ceiling -> unusable
    ranked = rank_by_window([bad, good])
    assert ranked[0] == good and ranked[-1] == bad


def test_pareto_trades_selectivity_against_safety_headroom():
    # fixed ceiling; selectivity (ratio) and safety headroom (ceiling/target) trade off.
    high_ratio = _result(8.0, {"n1": 40.0})  # ratio 5.0, headroom ~3.1
    dominated = _result(20.0, {"n1": 30.0})  # ratio 1.5, headroom ~1.2 (worse on both)
    high_headroom = _result(4.0, {"n1": 8.0})  # ratio 2.0, headroom ~6.2
    front = pareto_selectivity_safety([high_ratio, dominated, high_headroom])
    assert len(front) == 2
    assert high_ratio in front and high_headroom in front
    assert dominated not in front


# --- end to end: real field reuse + caching (NEURON) ------------------------


class _CountingBackend:
    name = "analytical"

    def __init__(self):
        self._inner = AnalyticalBackend()
        self.calls = 0

    def transfer_matrix(self, array, conductivity, query_points_um):
        self.calls += 1
        return self._inner.transfer_matrix(array, conductivity, query_points_um)


@pytest.mark.neuron
def test_sweep_reuses_fields_across_configs_and_caches(neuron_h, tmp_path):
    patch = spec.RetinalPatch(
        cells=(
            spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),
            spec.RGC(id="n1", cell_type="parasol_on", soma_um=(40.0, 0.0, -20.0)),
            spec.RGC(id="far", cell_type="parasol_on", soma_um=(500.0, 0.0, -20.0)),
        ),
        target_id="t",
        optic_disc_um=(2000.0, 0.0, -20.0),
    )
    configs = waveform_shape_sweep({"e": -1.0}, [200.0, 100.0])  # two distinct configs
    store = Project.open(tmp_path / "proj")

    spy = _CountingBackend()
    first = sweep(ARR, patch, COND, configs, store=store, backend=spy)
    assert first.n_evaluated == 2 and first.n_cached == 0
    assert all(res.activated for res in first.results)
    # target + one in-radius off-target, each field solved once — reused across both configs
    assert spy.calls == 2

    spy2 = _CountingBackend()
    second = sweep(ARR, patch, COND, configs, store=store, backend=spy2)
    assert second.n_cached == 2 and second.n_evaluated == 0
    assert spy2.calls == 0  # all served from the store — no field solves at all
    assert {r.result_key for r in second.results} == {r.result_key for r in first.results}
