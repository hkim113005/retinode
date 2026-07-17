"""The FastAPI app factory.

``create_app`` wires the routes over the engine. The threshold provider (what the
scorecard uses) is injectable so tests pass a fast fake instead of the real NEURON
population solve; production defaults to the real one, imported lazily so the field-
only path (and the no-NEURON test env) never pulls the cable engine.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .jobs import JobRegistry
from .routes import compare, score


def _default_provider() -> Callable[..., Any]:
    # Lazy: keeps `import api` (and the field-only path) free of the cable engine,
    # so the fast test job — which installs no NEURON — imports the API cleanly.
    from engine.cable.population import population_thresholds

    return population_thresholds


def create_app(*, thresholds_provider: Callable[..., Any] | None = None) -> FastAPI:
    """Build the API. Pass ``thresholds_provider`` to override the scorecard's
    threshold source (tests inject a fast fake; None → the real population solve)."""
    app = FastAPI(title="Retinode API", version="0.1.0")
    app.state.thresholds_provider = thresholds_provider or _default_provider()
    app.state.jobs = JobRegistry()

    # Dev CORS: the Vite client runs on a different origin (S2). Tightened later.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(compare.router)
    app.include_router(score.router)
    return app
