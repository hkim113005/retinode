"""P2 S5: pre-sweep cost estimation — arithmetic (fast) and a one-cell benchmark."""

import pytest

from engine import spec
from engine.study.cost import (
    CellBenchmark,
    estimate_from_benchmark,
    estimate_sweep_cost,
    format_duration,
)

COND = spec.HomogeneousConductivity(sigma_S_per_m=1.0)
ARR = spec.ElectrodeArray(
    electrodes=(spec.Electrode(id="e", pos_um=(0.0, 0.0, 0.0), shape="disk", size_um=10.0),)
)
CFG = spec.StimConfig.from_map(
    {"e": -1.0}, waveform=spec.Waveform(phase_width_us=200.0), distant_return=True
)


# --- the cost arithmetic (pure) ---------------------------------------------


def test_cost_is_solves_plus_threshold_searches():
    est = estimate_sweep_cost(10, 2, 3.0, per_solve_s=1.0)
    assert est.field_solve_s == 2.0  # n_cells * per_solve
    assert est.threshold_s == 60.0  # 10 configs * 2 cells * 3 s
    assert est.total_s == 62.0
    assert est.n_to_evaluate == 10 and est.n_cached == 0


def test_cached_configs_are_not_counted():
    est = estimate_sweep_cost(10, 2, 3.0, n_cached=4)
    assert est.n_to_evaluate == 6
    assert est.threshold_s == 36.0  # only the 6 un-cached configs
    assert est.field_solve_s == 0.0  # default per_solve is negligible


def test_cache_count_is_clamped_to_the_config_range():
    assert estimate_sweep_cost(5, 1, 2.0, n_cached=99).n_to_evaluate == 0  # all cached
    assert estimate_sweep_cost(5, 1, 2.0, n_cached=-3).n_cached == 0  # never negative


def test_estimate_from_benchmark_uses_measured_times():
    bench = CellBenchmark(per_solve_s=0.5, per_threshold_s=4.0)
    est = estimate_from_benchmark(5, 2, bench)
    assert est.field_solve_s == 1.0  # 2 cells * 0.5
    assert est.threshold_s == 40.0  # 5 * 2 * 4.0
    assert est.total_s == 41.0


def test_human_summary_reads_naturally():
    text = estimate_sweep_cost(500, 3, 5.5, n_cached=120).human()
    assert "500 configs" in text and "120 cached" in text and "3 cells" in text


def test_format_duration():
    assert format_duration(0) == "0s"
    assert format_duration(9) == "9s"
    assert format_duration(150) == "2m 30s"
    assert format_duration(3930) == "1h 5m 30s"
    assert format_duration(-5) == "0s"  # never negative


# --- the benchmark (NEURON) -------------------------------------------------


@pytest.mark.neuron
def test_benchmark_cell_measures_positive_times(neuron_h):
    from engine.study.cost import benchmark_cell

    patch = spec.RetinalPatch(
        cells=(spec.RGC(id="t", cell_type="parasol_on", soma_um=(0.0, 0.0, -20.0)),),
        target_id="t",
        optic_disc_um=(2000.0, 0.0, -20.0),
    )
    bench = benchmark_cell(patch, ARR, CFG, COND)
    assert bench.per_solve_s > 0.0 and bench.per_threshold_s > 0.0
    # the NEURON threshold search dominates the analytical field solve
    assert bench.per_threshold_s > bench.per_solve_s
    # and it feeds a sensible sweep estimate
    est = estimate_from_benchmark(100, 3, bench)
    assert est.total_s > 0.0 and est.n_to_evaluate == 100
