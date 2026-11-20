from collections.abc import Callable
from pathlib import Path

import httpx
from fastapi import FastAPI

from arzi.config import Settings
from tests.conftest import AppFactory
from tests.fakes import FakeProbe

ClientFor = Callable[[FastAPI], httpx.AsyncClient]


async def test_healthz_is_ok_without_touching_dependencies(
    make_app: AppFactory, client_for: ClientFor
) -> None:
    probe = FakeProbe("firestore", error=RuntimeError("down"))
    async with client_for(make_app([probe])) as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "build_sha": "dev"}
    assert probe.calls == 0


async def test_readyz_is_ready_when_nothing_is_configured(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"ready": True, "checks": []}


async def test_readyz_reports_each_dependency(make_app: AppFactory, client_for: ClientFor) -> None:
    probes = [FakeProbe("firestore"), FakeProbe("storage")]
    async with client_for(make_app(probes)) as client:
        body = (await client.get("/readyz")).json()

    assert body["ready"] is True
    assert [(c["name"], c["state"]) for c in body["checks"]] == [
        ("firestore", "ok"),
        ("storage", "ok"),
    ]


async def test_readyz_returns_503_and_hides_error_text(
    make_app: AppFactory, client_for: ClientFor
) -> None:
    probes = [FakeProbe("firestore"), FakeProbe("storage", error=PermissionError("gs://secret"))]
    async with client_for(make_app(probes)) as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    failed = response.json()["checks"][1]
    assert failed == {**failed, "state": "failed", "detail": "PermissionError"}
    assert "secret" not in response.text


async def test_health_routes_take_precedence_over_the_spa(
    tmp_path: Path, settings: Settings, make_app: AppFactory, client_for: ClientFor
) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    app = make_app(app_settings=settings.model_copy(update={"static_dir": tmp_path}))

    async with client_for(app) as client:
        response = await client.get("/healthz")

    assert response.json()["status"] == "ok"


async def test_health_alias_matches_healthz(client: httpx.AsyncClient) -> None:
    alias = await client.get("/health")
    original = await client.get("/healthz")

    assert alias.status_code == 200
    assert alias.json() == original.json()
