"""Surrogate-guided geometry search (P5 S6, optional).

A full geometry grid is wasteful: most of the selectivity/safety signal lives in a
small region of (diameter, pitch), and each geometry costs a field solve plus a
population of NEURON threshold searches. This module fits a **Gaussian-process
emulator** over ``geometry -> score`` from the geometries evaluated so far and uses
it to **propose the next geometry to evaluate** (upper-confidence-bound active
learning), so the search spends its evaluations where the score is high or the
model is uncertain, converging on the Pareto-relevant region without touching most
of the grid.

The GP is a plain RBF-kernel regressor in numpy/scipy (no new dependency): it
standardises the inputs (so one length scale works across diameter ~10 µm and
pitch ~30 µm), and returns a posterior mean and standard deviation. The search is
**deterministic**: seeds are an even spread of the candidate set and every step is
an ``argmax``, so a run is reproducible and testable.

The expensive evaluation is injected (`evaluate(index) -> score`): a synthetic
function in tests, a real geometry sweep's selectivity in use. What "score" means
(selectivity, a weighted objective, ...) is the caller's choice.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
from scipy.linalg import cho_factor, cho_solve

from .geometry import ArrayGeometry


@dataclass(frozen=True)
class GPModel:
    """A fitted RBF Gaussian process. Opaque; build via :func:`fit_gp`."""

    x_train: np.ndarray  # (n, d), standardised
    x_mean: np.ndarray  # (d,) standardisation of the inputs
    x_std: np.ndarray  # (d,)
    y_mean: float  # outputs are centred before conditioning
    length_scale: float
    signal_var: float
    cho: tuple  # cholesky factor of K (from scipy.cho_factor)
    alpha: np.ndarray  # cho_solve(K, y - y_mean)


def _rbf(a: np.ndarray, b: np.ndarray, length_scale: float, signal_var: float) -> np.ndarray:
    d2 = np.sum(a**2, 1)[:, None] + np.sum(b**2, 1)[None, :] - 2.0 * a @ b.T
    return signal_var * np.exp(-0.5 * np.maximum(d2, 0.0) / length_scale**2)


def fit_gp(
    x: np.ndarray,
    y: np.ndarray,
    *,
    length_scale: float = 1.0,
    signal_var: float = 1.0,
    noise_var: float = 1e-6,
) -> GPModel:
    """Fit a GP to observations ``(x, y)``. Inputs are standardised per dimension
    so one ``length_scale`` is sensible across differently-scaled knobs."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float).reshape(-1)
    x = x.reshape(len(y), -1)
    x_mean = x.mean(axis=0)
    x_std = x.std(axis=0)
    x_std[x_std == 0.0] = 1.0  # a constant dimension contributes nothing, not a divide-by-zero
    xs = (x - x_mean) / x_std
    y_mean = float(y.mean())
    k = _rbf(xs, xs, length_scale, signal_var) + noise_var * np.eye(len(y))
    cho = cho_factor(k, lower=True)
    alpha = cho_solve(cho, y - y_mean)
    return GPModel(xs, x_mean, x_std, y_mean, length_scale, signal_var, cho, alpha)


def predict(model: GPModel, x_star: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Posterior mean and standard deviation at ``x_star`` (shape (m, d) or (d,))."""
    xs = np.asarray(x_star, dtype=float).reshape(-1, model.x_train.shape[1])
    xs = (xs - model.x_mean) / model.x_std
    k_star = _rbf(xs, model.x_train, model.length_scale, model.signal_var)  # (m, n)
    mean = k_star @ model.alpha + model.y_mean
    v = cho_solve(model.cho, k_star.T)  # (n, m)
    var = model.signal_var - np.sum(k_star * v.T, axis=1)  # k(x*,x*)=signal_var for RBF
    std = np.sqrt(np.maximum(var, 0.0))
    return mean, std


def upper_confidence_bound(mean: np.ndarray, std: np.ndarray, kappa: float = 2.0) -> np.ndarray:
    """The UCB acquisition: ``mean + kappa * std``. Higher ``kappa`` explores more."""
    return mean + kappa * std


def propose_index(
    model: GPModel, candidates: np.ndarray, *, kappa: float = 2.0, exclude: set[int] | None = None
) -> int:
    """Index of the highest-UCB candidate not already sampled."""
    exclude = exclude or set()
    mean, std = predict(model, candidates)
    for i in np.argsort(-upper_confidence_bound(mean, std, kappa)):
        if int(i) not in exclude:
            return int(i)
    raise ValueError("every candidate has already been sampled")


@dataclass(frozen=True)
class SearchTrace:
    """The record of an active search: what was sampled, in order, and the best."""

    sampled_indices: tuple[int, ...]
    scores: tuple[float, ...]  # aligned with sampled_indices
    best_index: int
    best_score: float

    @property
    def n_evaluated(self) -> int:
        return len(self.sampled_indices)


def _spread_indices(n: int, k: int) -> list[int]:
    """``k`` indices spread evenly across ``range(n)`` (deterministic seeds)."""
    k = min(k, n)
    if k <= 1:
        return [n // 2]
    return sorted({int(i) for i in np.linspace(0, n - 1, k).round().astype(int)})


def active_search(
    candidates: np.ndarray,
    evaluate: Callable[[int], float],
    *,
    n_seed: int = 3,
    n_iter: int = 6,
    kappa: float = 1.5,
    length_scale: float = 1.0,
    signal_var: float = 1.0,
    noise_var: float = 1e-6,
) -> SearchTrace:
    """UCB active search over ``candidates`` (shape (n, d)). Evaluate an even
    spread of ``n_seed`` seeds, then up to ``n_iter`` times: fit the GP, propose the
    highest-UCB unsampled candidate, evaluate it. ``evaluate(i)`` scores candidate
    ``i`` (the expensive step). Deterministic given the inputs."""
    x = np.asarray(candidates, dtype=float)
    if len(x) == 0:
        raise ValueError("no candidates to search")
    x = x.reshape(len(x), -1)
    n = len(x)

    sampled = _spread_indices(n, n_seed)
    scores = [float(evaluate(i)) for i in sampled]
    for _ in range(n_iter):
        if len(sampled) >= n:
            break
        model = fit_gp(
            x[sampled], np.array(scores),
            length_scale=length_scale, signal_var=signal_var, noise_var=noise_var,
        )
        nxt = propose_index(model, x, kappa=kappa, exclude=set(sampled))
        sampled.append(nxt)
        scores.append(float(evaluate(nxt)))

    best = int(np.argmax(scores))
    return SearchTrace(tuple(sampled), tuple(scores), sampled[best], scores[best])


# --- geometry adapter -------------------------------------------------------


def geometry_params(geometries: Sequence[ArrayGeometry]) -> np.ndarray:
    """The (diameter, pitch) matrix a surrogate optimises over: the continuous
    geometry knobs. Arrangement/aperture are held fixed within one search."""
    return np.array([[g.diameter_um, g.pitch_um] for g in geometries], dtype=float)


def search_geometries(
    geometries: Sequence[ArrayGeometry],
    score_of: Callable[[ArrayGeometry], float],
    *,
    n_seed: int = 3,
    n_iter: int = 6,
    kappa: float = 1.5,
    length_scale: float = 1.0,
) -> tuple[ArrayGeometry, SearchTrace]:
    """Active-learning search over a candidate geometry set: fit a GP over
    (diameter, pitch) -> ``score_of(geometry)`` and propose the next geometry by
    UCB, converging on the high-score region without evaluating the whole grid.
    Returns the best geometry found and the search trace. ``score_of`` is the
    expensive evaluation (a real geometry sweep's selectivity, or a stub)."""
    geometries = list(geometries)
    trace = active_search(
        geometry_params(geometries),
        lambda i: score_of(geometries[i]),
        n_seed=n_seed, n_iter=n_iter, kappa=kappa, length_scale=length_scale,
    )
    return geometries[trace.best_index], trace
