"""Application factory.

Run locally with ``uvicorn arzi.main:create_app --factory``. One container serves both the API
and, when ``ARZI_STATIC_DIR`` is set, the built single-page app (ADR-0007).
"""

from collections.abc import MutableMapping, Sequence
from typing import Any

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response

from arzi.adapters.readiness_probes import build_readiness_probes
from arzi.api.errors import register_error_handlers
from arzi.api.request_id import request_id_middleware
from arzi.api.routers import appeals, claims, demo, health, meta, runs
from arzi.bootstrap import Services, build_services
from arzi.config import Settings, get_settings
from arzi.services.readiness import ReadinessProbe

Scope = MutableMapping[str, Any]


def _client_route(path: str) -> bool:
    """A path the SPA router owns (``claims/ARZ-…``), as opposed to an API call or a file."""
    first, _, _ = path.partition("/")
    return first not in {"api", "assets"} and "." not in path.rsplit("/", 1)[-1]


class SpaFiles(StaticFiles):
    """The built SPA: hashed assets cached for a year, ``index.html`` never cached, and client
    routes answered with ``index.html`` so a reload or a shared link opens the right screen.
    Missing files and unknown API paths stay 404 problems."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        path = path.replace("\\", "/")  # Starlette passes an OS path (backslashes on Windows)
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not _client_route(path):
                raise
            response = await super().get_response("index.html", scope)
        if path.startswith("assets/") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


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
    app.include_router(demo.router)

    if settings.static_dir is not None:
        # Mounted last so API and health routes always take precedence.
        app.mount("/", SpaFiles(directory=settings.static_dir, html=True), name="spa")
    return app
