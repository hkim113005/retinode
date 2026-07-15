"""P2 S2: the result store round-trips sidecars and maintains a queryable index."""

import pytest

from engine.store import StoreError
from engine.store.results import ResultStore


def test_result_round_trip(tmp_path, result_windowed):
    rs = ResultStore(tmp_path / "results")
    r = result_windowed
    assert r.result_key not in rs and rs.get(r.result_key) is None
    rs.put(r)
    assert r.result_key in rs
    assert rs.get(r.result_key) == r  # full-fidelity reload from the JSON sidecar


def test_index_has_one_populated_row_per_result(tmp_path, result_windowed, result_unbounded):
    rs = ResultStore(tmp_path / "r")
    rs.put(result_windowed)
    rs.put(result_unbounded)
    idx = rs.index()
    assert idx.num_rows == 2
    rows = {row["result_key"]: row for row in idx.to_pylist()}
    assert set(rows) == {result_windowed.result_key, result_unbounded.result_key}
    # scalar columns are extracted for querying/ranking (P2 S4)
    assert rows[result_windowed.result_key]["window_hi_uA"] == pytest.approx(12.0)
    assert rows[result_windowed.result_key]["limiting"] == "off_target"
    assert rows[result_unbounded.result_key]["off_min_uA"] == float("inf")


def test_put_is_an_idempotent_upsert(tmp_path, result_windowed):
    rs = ResultStore(tmp_path / "r")
    rs.put(result_windowed)
    rs.put(result_windowed)  # storing the same key again must not duplicate the row
    assert rs.index().num_rows == 1


def test_inactive_result_indexes_with_nulls(tmp_path, result_inactive):
    rs = ResultStore(tmp_path / "r")
    rs.put(result_inactive)
    row = rs.index().to_pylist()[0]
    assert row["activated"] is False
    assert row["window_hi_uA"] is None and row["limiting"] is None


def test_corrupt_sidecar_raises_store_error(tmp_path, result_windowed):
    rs = ResultStore(tmp_path / "r")
    rs._json_path(result_windowed.result_key).write_text("{ not valid json")
    with pytest.raises(StoreError, match="corrupt result sidecar"):
        rs.get(result_windowed.result_key)
