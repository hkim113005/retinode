"""P5 S6: surrogate-guided geometry search (GP, acquisition, active search)."""

from __future__ import annotations

import numpy as np
import pytest

from engine.study.geometry import geometry_grid
from engine.study.surrogate import (
    active_search,
    fit_gp,
    geometry_params,
    predict,
    propose_index,
    search_geometries,
    upper_confidence_bound,
)


def test_gp_interpolates_training_points_and_is_uncertain_away():
    x = np.array([[0.0], [1.0], [2.0], [3.0]])
    y = np.array([0.0, 1.0, 0.0, -1.0])
    model = fit_gp(x, y, length_scale=1.0, noise_var=1e-9)
    mean, std = predict(model, x)
    assert np.allclose(mean, y, atol=1e-3)  # near-exact at the training inputs
    assert np.max(std) < 1e-3  # ~certain there
    _, std_mid = predict(model, np.array([[0.5]]))
    assert std_mid[0] > 1e-3  # uncertain between training points


def test_ucb_trades_mean_against_uncertainty():
    mean = np.array([1.0, 1.0])
    std = np.array([0.0, 0.5])
    acq = upper_confidence_bound(mean, std, kappa=2.0)
    assert acq[1] > acq[0]  # equal mean, the more uncertain point is preferred


def test_propose_index_picks_top_ucb_and_skips_sampled():
    x = np.array([[0.0], [1.0], [2.0]])
    y = np.array([0.0, 5.0, 0.0])  # candidate 1 is clearly best
    model = fit_gp(x, y, length_scale=1.0)
    assert propose_index(model, x, kappa=0.0) == 1  # pure exploitation -> the peak
    assert propose_index(model, x, kappa=0.0, exclude={1}) in (0, 2)  # skips it


def _bump(g):
    # a broad optimum near (12, 30), a stand-in for the selectivity surface
    return float(np.exp(-((g.diameter_um - 12) ** 2 / 50 + (g.pitch_um - 30) ** 2 / 200)))


CANDS = geometry_grid(
    diameters_um=[8.0, 10.0, 12.0, 14.0, 16.0, 18.0],
    pitches_um=[20.0, 25.0, 30.0, 35.0, 40.0, 45.0],
    arrangement="grid",
    aperture_um=60.0,
)


def test_active_search_finds_a_near_optimum_with_fewer_evaluations():
    opt = max(_bump(g) for g in CANDS)
    best, trace = search_geometries(CANDS, _bump, n_seed=3, n_iter=8, kappa=1.5, length_scale=1.0)
    assert trace.n_evaluated < len(CANDS)  # the whole point: not a full grid
    assert trace.best_score >= 0.9 * opt  # lands near the true optimum
    assert trace.best_score > max(trace.scores[:3])  # beats sampling seeds alone
    assert _bump(best) == pytest.approx(trace.best_score)


def test_active_search_is_deterministic():
    a = active_search(geometry_params(CANDS), lambda i: _bump(CANDS[i]), n_seed=3, n_iter=5)
    b = active_search(geometry_params(CANDS), lambda i: _bump(CANDS[i]), n_seed=3, n_iter=5)
    assert a == b  # same seeds, same argmax steps -> identical trace


def test_search_counts_each_geometry_at_most_once():
    seen: list[int] = []
    search_geometries(CANDS, lambda g: (seen.append(id(g)), _bump(g))[1], n_seed=3, n_iter=6)
    assert len(seen) == len(set(seen))  # no geometry evaluated twice


def test_geometry_params_extracts_diameter_and_pitch():
    x = geometry_params(CANDS)
    assert x.shape == (len(CANDS), 2)
    assert (x[:, 0] == np.array([g.diameter_um for g in CANDS])).all()
    assert (x[:, 1] == np.array([g.pitch_um for g in CANDS])).all()


def test_empty_candidate_set_is_rejected():
    with pytest.raises(ValueError, match="no candidates"):
        active_search(np.empty((0, 2)), lambda i: 0.0)
