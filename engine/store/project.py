"""A project: the on-disk workspace tying specs, fields, results, and manifest.

The layout is the deliberately boring, inspectable one from project plan §10:

    <root>/
      specs/            canonical JSON, one file per spec, hash in the name
      cache/fields/     transfer matrices (A), HDF5, by field_key
      results/          JSON sidecars + index.parquet, by result_key
      project.json      manifest: schema version, created/updated timestamps

``open`` creates the workspace if absent. Reads return ``None`` on a miss (never
a surprise), and a present ``result_key`` is a cache hit the sweep uses to skip a
re-solve. Provenance (the append-only log) lands in P2 S3.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from engine.spec.hashing import spec_hash
from engine.spec.serialization import from_json, to_json

from .fields import FieldCache
from .provenance import ProvenanceLog, RunRecord, make_run_record
from .results import ResultStore

if TYPE_CHECKING:
    from engine.eval.result import EvaluationResult

PROJECT_SCHEMA_VERSION = 1


class Project:
    """A saved workspace: content-addressed specs, field cache, and result store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.specs_dir = self.root / "specs"
        self.specs_dir.mkdir(parents=True, exist_ok=True)
        self.fields = FieldCache(self.root / "cache" / "fields")
        self.results = ResultStore(self.root / "results")
        self.provenance = ProvenanceLog(self.root / "provenance.log")
        self._init_manifest()

    @classmethod
    def open(cls, root: str | Path) -> Project:
        """Open the project at ``root``, creating the layout if it does not exist."""
        return cls(root)

    # --- manifest ----------------------------------------------------------

    @property
    def _manifest_path(self) -> Path:
        return self.root / "project.json"

    def _init_manifest(self) -> None:
        if not self._manifest_path.exists():
            now = _now()
            self._write_manifest(
                {"schema_version": PROJECT_SCHEMA_VERSION, "created": now, "updated": now}
            )

    def manifest(self) -> dict[str, Any]:
        return json.loads(self._manifest_path.read_text())

    def _write_manifest(self, m: dict[str, Any]) -> None:
        self._manifest_path.write_text(json.dumps(m, indent=2, sort_keys=True))

    def _touch(self) -> None:
        m = self.manifest()
        m["updated"] = _now()
        self._write_manifest(m)

    # --- specs -------------------------------------------------------------

    def put_spec(self, obj: Any) -> str:
        """Store a spec object canonically (hash-named); return its content hash."""
        h = spec_hash(obj)
        path = self.specs_dir / f"{h}.json"
        if not path.exists():
            path.write_text(to_json(obj))
        return h

    def get_spec(self, spec_hash_: str) -> Any | None:
        path = self.specs_dir / f"{spec_hash_}.json"
        return from_json(path.read_text()) if path.exists() else None

    # --- fields ------------------------------------------------------------

    def put_field(self, field_key: str, a: np.ndarray, *, backend_name: str = "") -> None:
        self.fields.put(field_key, a, backend_name=backend_name)
        self._touch()

    def get_field(self, field_key: str) -> np.ndarray | None:
        return self.fields.get(field_key)

    def has_field(self, field_key: str) -> bool:
        return field_key in self.fields

    # --- results -----------------------------------------------------------

    def put_result(self, result: EvaluationResult) -> None:
        self.results.put(result)
        self._touch()

    def get_result(self, result_key: str) -> EvaluationResult | None:
        return self.results.get(result_key)

    def has_result(self, result_key: str) -> bool:
        return result_key in self.results

    # --- a full run: result + spec values + provenance ---------------------

    def record_run(
        self,
        result: EvaluationResult,
        *,
        array: Any,
        config: Any,
        patch: Any,
        off_target_set: Any,
        conductivity: Any,
        backend_name: str = "analytical",
        seeds: dict[str, Any] | None = None,
        solve_params: str | None = None,
        eval_params: str | None = None,
    ) -> RunRecord:
        """Persist an evaluation completely: the result, the spec *values* behind
        its hashes, and an append-only provenance record that replays its keys.

        This is the one call a sweep makes per evaluation, so every stored result
        has a matching provenance entry. The off-target set is captured inside the
        record (it is not a registry spec type); the other specs go to ``specs/``.
        """
        self.put_result(result)
        for obj in (array, config, patch, conductivity):
            self.put_spec(obj)
        record = make_run_record(
            result,
            solve_params=solve_params,
            eval_params=eval_params,
            array=array,
            conductivity=conductivity,
            off_target_set=off_target_set,
            backend_name=backend_name,
            seeds=seeds,
        )
        self.provenance.append(record)
        self._touch()
        return record


def _now() -> str:
    return datetime.now(UTC).isoformat()
