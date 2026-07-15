"""The project store: content-addressed persistence and provenance.

Kept import-light on purpose — importing ``engine.store`` (and ``engine.store.keys``,
which the evaluator uses) must not pull in the heavy ``store`` extra (``h5py`` /
``pyarrow``). The on-disk pieces live in submodules (``fields``, ``results``,
``project``) that are imported explicitly by store users, so the numpy-only core
stays importable without the extra installed.
"""

from __future__ import annotations


class StoreError(Exception):
    """A stored artifact is missing where required, unreadable, or corrupt."""
