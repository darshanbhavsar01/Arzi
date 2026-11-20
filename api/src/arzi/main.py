"""Application factory.

Run locally with ``uvicorn arzi.main:create_app --factory``. One container serves both the API
and, when ``ARZI_STATIC_DIR`` is set, the built single-page app (ADR planned in Phase 5).
"""

from collections.abc import Sequence

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from arzi.adapters.readiness_probes import build_readiness_probes
from arzi.api.errors import register_error_handlers
from arzi.api.request_id import request_id_middleware
from arzi.api.routers import appeals, claims, health, meta, runs
from arzi.bootstrap import Services, build_services
from arzi.config import Settings, get_settings
from arzi.services.readiness import ReadinessProbe


def create_app(
    settings: Settings | None = None,
    *,
    readiness_probes: Sequence[ReadinessProbe] | None = None,
    services: Services | None = None,
) -> FastAPI:
    """Build the ASGI app; tests pass settings, fake probes and services, production none."""
    settings = settings or get_settings()
    app = FastAPI(
        title="Arzi API",
        version="0.1.0",
        summary="Health-insurance claim audit and appeal decision support.",
    )
    app.state.settings = settings
    app.state.readiness_probes = (
        list(readiness_probes) if readiness_probes is not None else build_readiness_probes(settings)
    )

    app.state.services = services or build_services(settings)

    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(claims.router)
    app.include_router(runs.router)
    app.include_router(appeals.router)
    app.include_router(meta.router)

    if settings.static_dir is not None:
        # Mounted last so API and health routes always take precedence.
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="spa")
    return app
