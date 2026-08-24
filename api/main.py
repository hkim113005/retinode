"""The FastAPI app factory.

``create_app`` wires the routes over the engine. The threshold provider (what the
scorecard uses) is injectable so tests pass a fast fake instead of the real NEURON
population solve; production defaults to the real one, imported lazily so the field-
only path (and the no-NEURON test env) never pulls the cable engine.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .jobs import JobRegistry
from .routes import compare, field, score, study, sweep, upload, validation


def _json_safe(obj: Any) -> Any:
    """Coerce a validation-error payload into something JSON can actually render.

    FastAPI's default handler echoes the offending input back in the 422 body, and
    Starlette renders JSON with ``allow_nan=False``. So a request carrying ``NaN`` or
    ``1e400`` made the *error response itself* raise, turning a clean 422 into a 500.
    The one input that most needed a clear message got the least clear one. Pydantic
    also puts the raw ``ValueError`` in each error's ``ctx``, which is not
    serializable either. Both hazards are inputs we do not control, so this is total:
    anything that is not a JSON primitive falls through to ``str``.
    """
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else repr(obj)
    if obj is None or isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return str(obj)


def _default_provider() -> Callable[..., Any]:
    # Lazy: keeps `import api` (and the field-only path) free of the cable engine,
    # so the fast test job, which installs no NEURON, imports the API cleanly.
    from engine.cable.population import population_thresholds

    return population_thresholds


def create_app(*, thresholds_provider: Callable[..., Any] | None = None) -> FastAPI:
    """Build the API. Pass ``thresholds_provider`` to override the scorecard's
    threshold source (tests inject a fast fake; None → the real population solve)."""
    app = FastAPI(title="Retinode API", version="0.1.0")
    app.state.thresholds_provider = thresholds_provider or _default_provider()
    # Whether a provider was EXPLICITLY injected (a fast fake). The study route needs
    # this, not the resolved provider: production runs the default real provider AND
    # must dispatch to the FEM env (geometry comparison is FEM-only), whereas an
    # injected fake short-circuits the field and runs in-process. "provider is None"
    # can't tell them apart: both are non-None by the time they reach a route.
    app.state.provider_injected = thresholds_provider is not None
    app.state.jobs = JobRegistry()

    # Dev CORS: the Vite client runs on a different origin (S2). Tightened later.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": _json_safe(exc.errors())})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(compare.router)
    app.include_router(score.router)
    app.include_router(field.router)
    app.include_router(study.router)
    app.include_router(sweep.router)
    app.include_router(validation.router)
    app.include_router(upload.router)
    return app
