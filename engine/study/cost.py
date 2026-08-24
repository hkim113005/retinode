"""Pre-sweep cost estimation: a safety feature for the user's time (§9).

Before launching a sweep, estimate how long it will take, so no one accidentally
starts a three-day job. The model matches how the sweep actually spends time (P2
S4): the fields are solved **once** per cell (reused across configs), then every
un-cached config runs one threshold search per cell.

    total ≈ n_cells · per_solve  +  (n_configs − n_cached) · n_cells · per_threshold

The two per-unit times come from a quick one-cell benchmark on the real patch;
the arithmetic is pure and testable without it. This is the minimal estimator. The
at-scale version (per-mesh FEM benchmark, realized-vs-estimated logging that
improves the estimate over time) is Phase 5.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from engine.cable.multisite import multisite_threshold
from engine.cable.placement import place_cell
from engine.cable.solved import solve_field
from engine.field import AnalyticalBackend, FieldBackend
from engine.spec import ConductivityModel, ElectrodeArray, RetinalPatch, StimConfig


def format_duration(seconds: float) -> str:
    """A compact human duration: ``12s`` / ``2m 30s`` / ``1h 5m``."""
    total = int(round(max(0.0, seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if s or not parts:
        parts.append(f"{s}s")
    return " ".join(parts)


@dataclass(frozen=True)
class CellBenchmark:
    """Measured per-cell costs on the real patch, for extrapolating a sweep."""

    per_solve_s: float  # one field solve (cheap on the analytical tier, heavy for FEM)
    per_threshold_s: float  # one multi-site threshold search over a solved field


@dataclass(frozen=True)
class CostEstimate:
    n_configs: int
    n_cached: int
    n_to_evaluate: int
    n_cells: int
    field_solve_s: float  # one-time: all cells' fields, solved once for the sweep
    threshold_s: float  # the searches: n_to_evaluate · n_cells · per_threshold
    total_s: float

    def human(self) -> str:
        return (
            f"~{format_duration(self.total_s)} to sweep {self.n_to_evaluate} of "
            f"{self.n_configs} configs over {self.n_cells} cells "
            f"({self.n_cached} cached)"
        )


def estimate_sweep_cost(
    n_configs: int,
    n_cells: int,
    per_threshold_s: float,
    *,
    per_solve_s: float = 0.0,
    n_cached: int = 0,
) -> CostEstimate:
    """Estimate a configuration sweep's wall-clock from per-unit times (pure).

    ``per_threshold_s`` is one cell's threshold search over an already-solved
    field; ``per_solve_s`` is one field solve (0 by default, since it is negligible
    on the analytical tier). Cached configs cost nothing.
    """
    n_cached = min(max(0, n_cached), n_configs)
    n_to_evaluate = n_configs - n_cached
    field_solve_s = n_cells * per_solve_s
    threshold_s = n_to_evaluate * n_cells * per_threshold_s
    return CostEstimate(
        n_configs=n_configs,
        n_cached=n_cached,
        n_to_evaluate=n_to_evaluate,
        n_cells=n_cells,
        field_solve_s=field_solve_s,
        threshold_s=threshold_s,
        total_s=field_solve_s + threshold_s,
    )


def estimate_from_benchmark(
    n_configs: int,
    n_cells: int,
    benchmark: CellBenchmark,
    *,
    n_cached: int = 0,
) -> CostEstimate:
    """Estimate a sweep's cost from a measured per-cell benchmark."""
    return estimate_sweep_cost(
        n_configs,
        n_cells,
        benchmark.per_threshold_s,
        per_solve_s=benchmark.per_solve_s,
        n_cached=n_cached,
    )


def benchmark_cell(
    patch: RetinalPatch,
    array: ElectrodeArray,
    config: StimConfig,
    conductivity: ConductivityModel,
    *,
    backend: FieldBackend | None = None,
) -> CellBenchmark:
    """Time one field solve and one threshold search on the patch's target cell.

    A quick, representative probe. It is approximate, since the true per-cell time
    varies with cell placement and how deep the search bisects, but it is enough to
    size a sweep.
    """
    backend = backend or AnalyticalBackend()
    cell = place_cell(patch.target(), optic_disc=patch.optic_disc_um)

    t0 = perf_counter()
    solved = solve_field(cell, array, conductivity, backend)
    per_solve_s = perf_counter() - t0

    t1 = perf_counter()
    multisite_threshold(cell, array, config, conductivity, solved=solved)
    per_threshold_s = perf_counter() - t1

    return CellBenchmark(per_solve_s=per_solve_s, per_threshold_s=per_threshold_s)
