import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
import pytest
from google.genai import errors
from pydantic import BaseModel

from arzi.adapters.genai_client import (
    GeminiLlmClient,
    RecordingLlmClient,
    ReplayLlmClient,
    cache_key,
)
from arzi.services.ports import FilePart, LlmRequest, LlmUnavailableError


class Answer(BaseModel):
    value: str


def _request(**overrides: Any) -> LlmRequest[Answer]:  # noqa: ANN401 - request fields
    fields: dict[str, Any] = {
        "prompt_ref": "extract_bill@v1",
        "system": "Transcribe.",
        "schema": Answer,
        "model": "flash-model",
        "files": (FilePart(data=b"%PDF-", mime_type="application/pdf", sha256="abc"),),
    }
    fields.update(overrides)
    return LlmRequest(**fields)


def _response(text: str = '{"value": "ok"}', parsed: object = None) -> SimpleNamespace:
    usage = SimpleNamespace(
        prompt_token_count=1200, candidates_token_count=80, thoughts_token_count=None
    )
    return SimpleNamespace(text=text, parsed=parsed, usage_metadata=usage)


class ScriptedModels:
    """Stands in for ``client.aio.models``: returns or raises the scripted outcomes in order."""

    def __init__(self, *outcomes: object) -> None:
        self._outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    async def generate_content(self, *, model: str, contents: Any, config: Any) -> Any:  # noqa: ANN401 - SDK shapes
        self.calls.append({"model": model, "contents": contents, "config": config})
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome == "hang":
            await anyio.sleep(10)
        return outcome


def _client(models: ScriptedModels, *, retries: int = 2) -> tuple[GeminiLlmClient, list[float]]:
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return GeminiLlmClient(models, timeout_s=0.05, max_retries=retries, sleep=fake_sleep), sleeps


def _api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


async def test_structured_output_and_usage() -> None:
    models = ScriptedModels(_response())
    client, _ = _client(models)
    result = await client.generate_structured(_request(thinking_budget=0))

    assert result.output == Answer(value="ok")
    assert (result.call.input_tokens, result.call.output_tokens, result.call.thinking_tokens) == (
        1200,
        80,
        0,
    )
    config = models.calls[0]["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_schema is Answer
    assert config.temperature == 0.1
    assert config.thinking_config.thinking_budget == 0
    assert models.calls[0]["model"] == "flash-model"


async def test_ai_studio_gets_gcs_files_inline() -> None:
    models = ScriptedModels(_response())
    client = GeminiLlmClient(models, timeout_s=1, max_retries=0, gcs_uris=False)
    part = FilePart(data=b"%PDF-", mime_type="application/pdf", sha256="x", uri="gs://bucket/doc")
    await client.generate_structured(_request(files=(part,)))
    assert models.calls[0]["contents"][0].inline_data.data == b"%PDF-"


async def test_parsed_instance_is_used_directly_and_gcs_files_go_by_uri() -> None:
    models = ScriptedModels(_response(text="", parsed=Answer(value="parsed")))
    client, _ = _client(models)
    part = FilePart(data=b"", mime_type="application/pdf", sha256="x", uri="gs://bucket/doc")
    result = await client.generate_structured(_request(files=(part,)))
    assert result.output.value == "parsed"
    assert models.calls[0]["contents"][0].file_data.file_uri == "gs://bucket/doc"


@pytest.mark.parametrize("code", [429, 500, 503])
async def test_retries_transient_errors_with_backoff(code: int) -> None:
    models = ScriptedModels(_api_error(code), _api_error(code), _response())
    client, sleeps = _client(models)
    result = await client.generate_structured(_request())
    assert result.output.value == "ok"
    assert len(sleeps) == 2
    assert 1 <= sleeps[0] <= 2
    assert 2 <= sleeps[1] <= 4


async def test_gives_up_after_the_retry_budget() -> None:
    client, _ = _client(ScriptedModels(*[_api_error(429)] * 3))
    with pytest.raises(LlmUnavailableError) as info:
        await client.generate_structured(_request())
    assert info.value.slug == "llm-rate-limited"


async def test_client_errors_are_not_retried() -> None:
    models = ScriptedModels(_api_error(400), _response())
    client, sleeps = _client(models)
    with pytest.raises(LlmUnavailableError) as info:
        await client.generate_structured(_request())
    assert info.value.slug == "llm-error"
    assert sleeps == []


async def test_timeouts_and_invalid_output_are_retried() -> None:
    client, _ = _client(ScriptedModels("hang", _response(text="not json"), _response()))
    assert (await client.generate_structured(_request())).output.value == "ok"
    client, _ = _client(ScriptedModels("hang"), retries=0)
    with pytest.raises(LlmUnavailableError) as info:
        await client.generate_structured(_request())
    assert info.value.slug == "llm-timeout"


def test_cache_key_depends_on_prompt_and_inputs_not_model() -> None:
    base = cache_key(_request())
    assert base == cache_key(_request(model="another-model"))
    assert base != cache_key(_request(prompt_ref="extract_bill@v2"))
    other = FilePart(data=b"", mime_type="application/pdf", sha256="def")
    assert base != cache_key(_request(files=(other,)))


async def test_record_then_replay(tmp_path: Path) -> None:
    recorder = RecordingLlmClient(
        _client(ScriptedModels(_response()))[0], tmp_path / "case_x" / "llm_cache"
    )
    recorded = await recorder.generate_structured(_request())
    files = list((tmp_path / "case_x" / "llm_cache").glob("*.json"))
    assert len(files) == 1
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["prompt_ref"] == "extract_bill@v1"
    assert saved["call"]["input_tokens"] == 1200

    replayed = await ReplayLlmClient(tmp_path).generate_structured(_request())
    assert replayed.output == recorded.output
    assert replayed.call.replayed
    assert replayed.call.cost_micro_inr == 0


async def test_replay_miss_is_an_error_not_a_live_call(tmp_path: Path) -> None:
    with pytest.raises(LlmUnavailableError) as info:
        await ReplayLlmClient(tmp_path).generate_structured(_request())
    assert info.value.slug == "replay-miss"
