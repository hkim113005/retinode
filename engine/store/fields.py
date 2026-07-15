"""The transfer-matrix (A) cache: one HDF5 file per field solve, by field_key.

A field solve (the transfer matrix over a placed cell's segments) is the
expensive artifact the FEM tier will produce, so it is cached content-addressed
by ``field_key`` — which, extended in P2 S1 (D6), includes the query points, so
each placed cell's ``A`` gets its own entry. Storing ``A`` lets a re-run of the
same placement reload the matrix instead of re-solving; the live segment refs are
rebuilt cheaply from the (deterministic) morphology and realigned by key.
"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from . import StoreError


class FieldCache:
    """HDF5-backed store of transfer matrices, keyed by ``field_key``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, field_key: str) -> Path:
        return self.root / f"{field_key}.h5"

    def __contains__(self, field_key: str) -> bool:
        return self._path(field_key).exists()

    def put(self, field_key: str, a: np.ndarray, *, backend_name: str = "") -> None:
        """Store the transfer matrix ``a`` (mV/µA) under ``field_key``."""
        arr = np.asarray(a, dtype=float)
        with h5py.File(self._path(field_key), "w") as f:
            f.create_dataset("A", data=arr)
            f.attrs["field_key"] = field_key
            f.attrs["backend_name"] = backend_name
            f.attrs["shape"] = arr.shape

    def get(self, field_key: str) -> np.ndarray | None:
        """Return the cached matrix, or ``None`` if this key was never stored."""
        path = self._path(field_key)
        if not path.exists():
            return None
        try:
            with h5py.File(path, "r") as f:
                return np.asarray(f["A"][()], dtype=float)
        except (OSError, KeyError) as exc:  # unreadable/corrupt HDF5, or missing dataset
            raise StoreError(f"corrupt field cache entry {field_key}: {exc}") from exc
