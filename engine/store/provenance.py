"""The provenance log: an append-only record of every run, so figures are traceable.

Each evaluation appends one JSON line (project plan §10): the content hashes that
identify it, the off-target set inline (it is not a registry spec type, so its
value travels with the record), the software versions and git commit that
produced it, any RNG seeds, and a timestamp. The record is self-checking — it
carries the components of ``field_key`` and ``result_key``, so it can *replay*
those keys and confirm it describes exactly the computation that ran.

The log is append-only: a re-run appends another line rather than mutating
history, so the file is a truthful record of what happened and when.
"""

from __future__ import annotations

import dataclasses
import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from engine.spec.hashing import combine, spec_hash

if TYPE_CHECKING:
    from engine.eval.result import EvaluationResult


@dataclass(frozen=True)
class RunRecord:
    """One run's provenance: hashes to replay the keys, plus the run environment."""

    result_key: str
    field_key: str
    array_hash: str
    conductivity_hash: str
    config_hash: str
    patch_hash: str
    offtarget_hash: str
    off_target_set: dict[str, Any]  # inline value (not a registry spec type)
    evaluator_version: str
    backend_name: str
    software: dict[str, str]  # python, numpy, retinode, (neuron if present)
    git_commit: str | None
    seeds: dict[str, Any]  # empty until a stochastic layer (Phase 3) adds RNG
    timestamp: str  # ISO 8601, UTC

    def replay_field_key(self) -> str:
        """Recompute field_key from the recorded components — must equal field_key."""
        return combine(self.backend_name, self.array_hash, self.conductivity_hash)

    def replay_result_key(self) -> str:
        """Recompute result_key from the recorded components — must equal result_key."""
        return combine(
            self.field_key,
            self.config_hash,
            self.patch_hash,
            self.evaluator_version,
            self.offtarget_hash,
        )


def software_versions() -> dict[str, str]:
    """Versions of the software that could change a result (best-effort)."""
    import platform

    versions = {"python": platform.python_version(), "numpy": np.__version__}
    try:
        from importlib.metadata import version

        versions["retinode"] = version("retinode")
    except Exception:  # not installed as a distribution
        versions["retinode"] = "unknown"
    try:
        import neuron  # optional: only when the cable engine is in use

        versions["neuron"] = neuron.__version__
    except Exception:
        pass
    return versions


def git_commit() -> str | None:
    """The retinode repo's HEAD sha, or None if git/the repo is unavailable."""
    repo = Path(__file__).resolve().parents[2]  # engine/store/provenance.py -> repo root
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return out.stdout.strip()
    except Exception:  # not a repo, git missing, or timeout
        return None


def make_run_record(
    result: EvaluationResult,
    *,
    array: Any,
    conductivity: Any,
    off_target_set: Any,
    backend_name: str,
    seeds: dict[str, Any] | None = None,
) -> RunRecord:
    """Assemble a provenance record for one evaluation and its run environment."""
    return RunRecord(
        result_key=result.result_key,
        field_key=result.field_key,
        array_hash=spec_hash(array),
        conductivity_hash=spec_hash(conductivity),
        config_hash=result.config_hash,
        patch_hash=result.patch_hash,
        offtarget_hash=result.offtarget_hash,
        off_target_set=dataclasses.asdict(off_target_set),
        evaluator_version=result.evaluator_version,
        backend_name=backend_name,
        software=software_versions(),
        git_commit=git_commit(),
        seeds=dict(seeds or {}),
        timestamp=datetime.now(UTC).isoformat(),
    )


class ProvenanceLog:
    """Append-only JSONL log of RunRecords."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: RunRecord) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record), sort_keys=True, ensure_ascii=False) + "\n")

    def records(self) -> list[RunRecord]:
        if not self.path.exists():
            return []
        out: list[RunRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(RunRecord(**json.loads(line)))
        return out

    def find(self, result_key: str) -> RunRecord | None:
        """The most recent record for ``result_key``, or None if never recorded."""
        match: RunRecord | None = None
        for r in self.records():
            if r.result_key == result_key:
                match = r
        return match

    def __len__(self) -> int:
        return len(self.records())
