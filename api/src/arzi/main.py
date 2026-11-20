"""Application factory.

Run locally with ``uvicorn arzi.main:create_app --factory``. One container serves both the API
and, when ``ARZI_STATIC_DIR`` is set, the built single-page app (ADR planned in Phase 5).
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from arzi.api.errors import register_error_handlers
from arzi.api.request_id import request_id_middleware
from arzi.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI app; tests pass settings, production reads the environment."""
    settings = settings or get_settings()
    app = FastAPI(
        title="Arzi API",
        version="0.1.0",
        summary="Health-insurance claim audit and appeal decision support.",
    )
    app.state.settings = settings

    app.middleware("http")(request_id_middleware)
    register_error_handlers(app)

    if settings.static_dir is not None:
        # Mounted last so API routes always take precedence.
        app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="spa")
    return app
