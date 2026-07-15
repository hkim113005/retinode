"""The result store: a full-fidelity JSON sidecar per result + a parquet index.

Two representations, each for a different job (project plan §10):

- **JSON sidecar** (``results/<result_key>.json``) is the source of truth — the
  complete ``EvaluationResult`` tree, so ``get`` round-trips it exactly.
- **parquet index** (``results/index.parquet``) is the flat scalar table one row
  per result, for querying and ranking across a sweep (P2 S4) without opening
  every sidecar.

``put`` writes both and is idempotent: re-storing the same ``result_key`` upserts
its index row rather than duplicating it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from engine.eval.result import EvaluationResult

from . import StoreError, serialize

# Flat scalar columns for the queryable index. Floats hold inf natively; string
# and bool columns are nullable (None where a result did not activate).
_SCHEMA = pa.schema(
    [
        ("result_key", pa.string()),
        ("evaluator_version", pa.string()),
        ("field_key", pa.string()),
        ("config_hash", pa.string()),
        ("patch_hash", pa.string()),
        ("offtarget_hash", pa.string()),
        ("activated", pa.bool_()),
        ("target_uA", pa.float64()),
        ("off_min_uA", pa.float64()),
        ("ratio", pa.float64()),
        ("margin_uA", pa.float64()),
        ("selective_hi_uA", pa.float64()),
        ("safety_ceiling_uA", pa.float64()),
        ("window_hi_uA", pa.float64()),
        ("usable_margin_uA", pa.float64()),
        ("limiting", pa.string()),
        ("safe_at_target", pa.bool_()),
    ]
)


def _scalar_row(r: EvaluationResult) -> dict[str, Any]:
    sow, w = r.sow, r.window
    return {
        "result_key": r.result_key,
        "evaluator_version": r.evaluator_version,
        "field_key": r.field_key,
        "config_hash": r.config_hash,
        "patch_hash": r.patch_hash,
        "offtarget_hash": r.offtarget_hash,
        "activated": r.activated,
        "target_uA": r.thresholds.target_threshold_uA,
        "off_min_uA": sow.off_min_uA if sow else None,
        "ratio": sow.ratio if sow else None,
        "margin_uA": sow.margin_uA if sow else None,
        "selective_hi_uA": w.selective_hi_uA if w else None,
        "safety_ceiling_uA": w.safety_ceiling_uA if w else None,
        "window_hi_uA": w.window_hi_uA if w else None,
        "usable_margin_uA": w.usable_margin_uA if w else None,
        "limiting": w.limiting if w else None,
        "safe_at_target": r.safety_at_target.safe if r.safety_at_target else None,
    }


class ResultStore:
    """JSON-sidecar + parquet-index store of ``EvaluationResult``s by result_key."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _json_path(self, result_key: str) -> Path:
        return self.root / f"{result_key}.json"

    @property
    def _index_path(self) -> Path:
        return self.root / "index.parquet"

    def __contains__(self, result_key: str) -> bool:
        return self._json_path(result_key).exists()

    def put(self, result: EvaluationResult) -> None:
        """Persist a result: full JSON sidecar + an upserted parquet index row."""
        self._json_path(result.result_key).write_text(serialize.dumps(result))
        rows = [r for r in self._index_rows() if r["result_key"] != result.result_key]
        rows.append(_scalar_row(result))
        pq.write_table(pa.Table.from_pylist(rows, schema=_SCHEMA), self._index_path)

    def get(self, result_key: str) -> EvaluationResult | None:
        """Return the exact stored result, or ``None`` if this key is absent."""
        path = self._json_path(result_key)
        if not path.exists():
            return None
        try:
            return serialize.loads(path.read_text())
        except (ValueError, KeyError) as exc:  # malformed/truncated JSON sidecar
            raise StoreError(f"corrupt result sidecar {result_key}: {exc}") from exc

    def _index_rows(self) -> list[dict[str, Any]]:
        if not self._index_path.exists():
            return []
        try:
            return pq.read_table(self._index_path).to_pylist()
        except (OSError, pa.ArrowInvalid) as exc:  # corrupt/truncated parquet
            raise StoreError(f"corrupt result index: {exc}") from exc

    def index(self) -> pa.Table:
        """The scalar-metrics table across all stored results (for ranking)."""
        return pa.Table.from_pylist(self._index_rows(), schema=_SCHEMA)
