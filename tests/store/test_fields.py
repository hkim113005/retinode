"""P2 S2: the HDF5 transfer-matrix cache round-trips and fails loudly on corruption."""

import numpy as np
import pytest

from engine.store import StoreError
from engine.store.fields import FieldCache


def test_field_round_trip(tmp_path):
    fc = FieldCache(tmp_path / "fields")
    a = np.array([[1.0, -2.0, 0.0], [3.5, 0.0, 7.25]])
    key = "field_abc123"
    assert key not in fc and fc.get(key) is None  # absent before put
    fc.put(key, a, backend_name="analytical")
    assert key in fc
    assert np.array_equal(fc.get(key), a)  # exact matrix comes back


def test_missing_key_returns_none(tmp_path):
    assert FieldCache(tmp_path / "f").get("never_stored") is None


def test_corrupt_entry_raises_store_error(tmp_path):
    fc = FieldCache(tmp_path / "f")
    fc._path("bad").write_text("this is not an HDF5 file")  # truncated/garbage
    with pytest.raises(StoreError, match="corrupt field cache"):
        fc.get("bad")
