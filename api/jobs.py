"""A small in-process job model for the API (P7 S3).

Long work (a NEURON threshold search, later an FEM solve) must not block the
request. A job is submitted, runs on a background thread, and is polled for
progress; its result is **cached by key**, so re-submitting the same scene is served
instantly. This is the seam the two-env FEM dispatch (D5) plugs into later; for now
the tasks run in-process (NEURON in the uv env).

Deliberately dependency-free (no Redis/Celery): a dict + a lock + a thread pool is
enough for a single-user bench tool, and it keeps the API importable in the fast
test job with no extra services.

Scope note: the job and result maps grow for the process lifetime; nothing is
evicted. That is acceptable and intentional for the single-user assumption above
(one researcher, a session's worth of jobs); a long-lived multi-user server would
want an LRU/TTL bound, but adding eviction here would only risk dropping an in-flight
job's entry for a problem this tool does not have.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

# A task is given a progress reporter (fraction 0..1, message) and returns its result.
ProgressFn = Callable[[float, str], None]
Task = Callable[[ProgressFn], Any]


@dataclass
class Job:
    id: str
    status: str  # "running" | "done" | "error"
    fraction: float
    message: str
    result: Any | None = None
    error: str | None = None
    cached: bool = False


class JobRegistry:
    """Submit tasks to a thread pool, track their progress, and cache results by key."""

    def __init__(self, max_workers: int = 2) -> None:
        self._jobs: dict[str, Job] = {}
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="job")

    def submit(self, key: str, task: Task) -> Job:
        """Start ``task`` (or return a finished job from cache for ``key``)."""
        with self._lock:
            if key in self._cache:
                job = Job(
                    uuid.uuid4().hex[:12], "done", 1.0, "cached", self._cache[key], cached=True
                )
                self._jobs[job.id] = job
                return job
            job = Job(uuid.uuid4().hex[:12], "running", 0.0, "queued")
            self._jobs[job.id] = job
        self._pool.submit(self._run, job.id, key, task)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _run(self, job_id: str, key: str, task: Task) -> None:
        def report(fraction: float, message: str) -> None:
            with self._lock:
                job = self._jobs[job_id]
                job.fraction = max(0.0, min(1.0, fraction))
                job.message = message

        try:
            result = task(report)
        except Exception as exc:  # noqa: BLE001 - the job records any failure for the client
            with self._lock:
                job = self._jobs[job_id]
                job.status, job.error, job.fraction, job.message = "error", str(exc), 1.0, "failed"
            return
        with self._lock:
            self._cache[key] = result
            job = self._jobs[job_id]
            job.result, job.status, job.fraction, job.message = result, "done", 1.0, "done"
