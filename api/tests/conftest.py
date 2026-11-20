from collections.abc import AsyncIterator, Callable, Sequence

import httpx
import pytest
from fastapi import FastAPI

from arzi.config import Settings
from arzi.main import create_app
from arzi.services.readiness import ReadinessProbe

AppFactory = Callable[..., FastAPI]


@pytest.fixture
def settings() -> Settings:
    """Local settings that ignore the developer's real environment."""
    return Settings(_env_file=None, google_cloud_project=None, bucket=None)


@pytest.fixture
def make_app(settings: Settings) -> AppFactory:
    def factory(
        probes: Sequence[ReadinessProbe] = (), app_settings: Settings | None = None
    ) -> FastAPI:
        return create_app(app_settings or settings, readiness_probes=probes)

    return factory


@pytest.fixture
async def client(make_app: AppFactory) -> AsyncIterator[httpx.AsyncClient]:
    async with _client_for(make_app()) as c:
        yield c


def _client_for(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
def client_for() -> Callable[[FastAPI], httpx.AsyncClient]:
    return _client_for
