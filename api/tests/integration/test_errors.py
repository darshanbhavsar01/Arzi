from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from arzi.api.request_id import REQUEST_ID_HEADER
from arzi.config import Settings
from tests.conftest import AppFactory

ClientFor = Callable[[FastAPI], httpx.AsyncClient]


async def test_request_id_is_generated_and_echoed(client: httpx.AsyncClient) -> None:
    generated = (await client.get("/healthz")).headers[REQUEST_ID_HEADER]
    supplied = await client.get("/healthz", headers={REQUEST_ID_HEADER: "abc12345-trace"})
    injected = await client.get("/healthz", headers={REQUEST_ID_HEADER: "bad id\nlog-forge"})

    assert len(generated) == 32
    assert supplied.headers[REQUEST_ID_HEADER] == "abc12345-trace"
    assert injected.headers[REQUEST_ID_HEADER] != "bad id\nlog-forge"


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/nope", headers={REQUEST_ID_HEADER: "req-00000001"})

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json() == {
        "type": "https://arzi.app/problems/not-found",
        "title": "Not Found",
        "status": 404,
        "detail": "Not Found",
        "request_id": "req-00000001",
    }


async def test_validation_error_names_fields_but_not_values(
    make_app: AppFactory, client_for: ClientFor
) -> None:
    app = make_app()

    @app.get("/echo")
    async def echo(count: int) -> int:
        return count

    async with client_for(app) as client:
        response = await client.get("/echo", params={"count": "PATIENT-NAME"})

    assert response.status_code == 422
    assert response.json()["type"].endswith("/validation-error")
    assert response.json()["detail"] == "Invalid fields: query.count"
    assert "PATIENT-NAME" not in response.text


async def test_unhandled_error_is_generic_problem(
    make_app: AppFactory, client_for: ClientFor, caplog: pytest.LogCaptureFixture
) -> None:
    app = make_app()

    @app.get("/boom")
    async def boom() -> None:
        # Built at runtime so the traceback's source line cannot contain the value itself.
        aadhaar_like = "-".join(["1234", "5678", "9012"])
        raise RuntimeError(f"Aadhaar {aadhaar_like}")

    async with client_for(app) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["type"].endswith("/internal-error")
    assert response.json()["request_id"] == response.headers[REQUEST_ID_HEADER]
    assert "1234-5678-9012" not in response.text
    assert "RuntimeError" in caplog.text
    assert "1234-5678-9012" not in caplog.text


async def test_static_spa_is_served_and_misses_are_problems(
    tmp_path: Path, settings: Settings, make_app: AppFactory, client_for: ClientFor
) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>Arzi</title>", encoding="utf-8")
    app = make_app(app_settings=settings.model_copy(update={"static_dir": tmp_path}))

    async with client_for(app) as client:
        index = await client.get("/")
        missing = await client.get("/assets/missing.js")

    assert index.status_code == 200
    assert "<title>Arzi</title>" in index.text
    assert missing.status_code == 404
    assert missing.headers["content-type"] == "application/problem+json"
