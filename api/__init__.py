"""Retinode API: a thin FastAPI surface over the engine (Phase 7).

The API imports the engine and the pure view-contract helpers; the engine never
imports back (guarded by ``tests/api/test_boundary.py``). This is what keeps the
React re-skin a re-skin, not a rewrite (docs/phase-7-plan.md, D1).

``create_app`` is imported lazily (PEP 562) so that ``api.fem_job`` (the subprocess
entry that runs in the *conda* FEM env) can be imported there without pulling in
FastAPI, which that env does not have.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["create_app"]

if TYPE_CHECKING:
    from .main import create_app


def __getattr__(name: str):
    if name == "create_app":
        from .main import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
