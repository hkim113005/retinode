"""Retinode API — a thin FastAPI surface over the engine (Phase 7).

The API imports the engine and the pure view-contract helpers; the engine never
imports back (guarded by ``tests/api/test_boundary.py``). This is what keeps the
React re-skin a re-skin, not a rewrite (docs/phase-7-plan.md, D1).
"""

from __future__ import annotations

from .main import create_app

__all__ = ["create_app"]
