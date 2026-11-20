"""Gemini on Vertex AI, plus record and replay wrappers.

``replay`` mode serves responses recorded from real calls (``demo_cases/*/llm_cache``), keyed
by the prompt version and a hash of the exact inputs. That is the venue-Wi-Fi fallback and keeps
tests free. A missing recording is an error, never a silent live call.
"""

import hashlib
import json
import logging
import random
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Protocol

import anyio
from pydantic import BaseModel, ValidationError

from arzi.domain.models import LlmCall
from arzi.services.ports import FilePart, LlmRequest, LlmResult, LlmUnavailableError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def cache_key(request: LlmRequest[Any]) -> str:
    """Stable across processes: prompt version, schema, text and file hashes. Not the model id,
    so a recording survives a model upgrade until someone re-records on purpose."""
    payload = {
        "prompt": request.prompt_ref,
        "schema": request.schema.__name__,
        "text": request.text,
        "files": [part.sha256 for part in request.files],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


# --------------------------------------------------------------------------- Vertex AI


class _AsyncModels(Protocol):
    async def generate_content(self, *, model: str, contents: Any, config: Any) -> Any: ...  # noqa: ANN401 - SDK types


Sleep = Callable[[float], Awaitable[None]]


class GeminiLlmClient:
    """``google-genai`` (Vertex AI or AI Studio) with structured output, timeout and retries.

    ``gcs_uris`` lets Vertex AI read uploaded files straight from Cloud Storage; AI Studio cannot,
    so it always receives the bytes inline.
    """

    def __init__(
        self,
        models: _AsyncModels,
        *,
        timeout_s: float,
        max_retries: int,
        gcs_uris: bool = True,
        sleep: Sleep = anyio.sleep,
    ) -> None:
        self._models = models
        self._gcs_uris = gcs_uris
        self._timeout_s = timeout_s
        self._max_retries = max_retries
        self._sleep = sleep

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        from google.genai import errors, types

        config = types.GenerateContentConfig(
            system_instruction=request.system,
            response_mime_type="application/json",
            response_schema=request.schema,
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
            # A negative budget leaves thinking at the model's default (some models cannot turn
            # it off and reject a zero budget).
            thinking_config=types.ThinkingConfig(thinking_budget=request.thinking_budget)
            if request.thinking_budget >= 0
            else None,
        )
        parts = _parts(types, request.files, gcs_uris=self._gcs_uris)
        contents = [*parts, request.text or "Extract the document."]
        for attempt in range(self._max_retries + 1):
            try:
                with anyio.fail_after(self._timeout_s):
                    response = await self._models.generate_content(
                        model=request.model, contents=contents, config=config
                    )
                return LlmResult(
                    output=_parse(request.schema, response), call=_usage(request, response)
                )
            except errors.APIError as exc:
                retryable = exc.code in RETRYABLE_STATUS
                slug = "llm-rate-limited" if exc.code == 429 else "llm-error"
            except TimeoutError:
                retryable, slug = True, "llm-timeout"
            except ValidationError:
                retryable, slug = True, "llm-invalid-output"
            logger.warning(
                "llm call %s failed (%s), attempt %d", request.prompt_ref, slug, attempt + 1
            )
            if not retryable or attempt == self._max_retries:
                raise LlmUnavailableError(slug)
            # Jittered exponential backoff: 1-2 s, then 2-4 s.
            await self._sleep((2**attempt) * (1 + random.random()))  # noqa: S311 - jitter only
        raise LlmUnavailableError("llm-error")  # pragma: no cover - loop always returns or raises


def _parts(types: Any, files: Sequence[FilePart], *, gcs_uris: bool) -> list[Any]:  # noqa: ANN401
    return [
        types.Part.from_uri(file_uri=f.uri, mime_type=f.mime_type)
        if gcs_uris and f.uri and f.uri.startswith("gs://")
        else types.Part.from_bytes(data=f.data, mime_type=f.mime_type)
        for f in files
    ]


def _parse[T: BaseModel](schema: type[T], response: Any) -> T:  # noqa: ANN401 - SDK response
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed
    return schema.model_validate_json(response.text or "")


def _usage(request: LlmRequest[Any], response: Any) -> LlmCall:  # noqa: ANN401 - SDK response
    usage = getattr(response, "usage_metadata", None)
    return LlmCall(
        prompt_ref=request.prompt_ref,
        model=request.model,
        input_tokens=getattr(usage, "prompt_token_count", None) or 0,
        output_tokens=getattr(usage, "candidates_token_count", None) or 0,
        thinking_tokens=getattr(usage, "thoughts_token_count", None) or 0,
    )


def vertex_models(project: str, location: str, timeout_s: float) -> _AsyncModels:
    """The SDK's async models API, created lazily so local modes never load credentials."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=project,
        location=location,
        http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
    )
    models: _AsyncModels = client.aio.models
    return models


def ai_studio_models(api_key: str, timeout_s: float) -> _AsyncModels:
    """The Gemini Developer API (AI Studio). Free tier: synthetic test data only."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        # JSON mode (structured output) is only enabled on v1beta for some AI Studio models.
        http_options=types.HttpOptions(timeout=int(timeout_s * 1000), api_version="v1beta"),
    )
    models: _AsyncModels = client.aio.models
    return models


# --------------------------------------------------------------------------- record / replay


class ReplayLlmClient:
    """Serves recorded responses; ``<root>/*/llm_cache/<key>.json``."""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        key = cache_key(request)
        matches = sorted(self._root.glob(f"*/llm_cache/{key}.json"))
        if not matches:
            raise LlmUnavailableError("replay-miss")
        recording = json.loads(matches[0].read_text(encoding="utf-8"))
        call = LlmCall.model_validate({**recording["call"], "replayed": True, "cost_micro_inr": 0})
        return LlmResult(output=request.schema.model_validate(recording["output"]), call=call)


class RecordingLlmClient:
    """Passes calls through and saves each response as a replay recording."""

    def __init__(self, inner: Any, directory: Path) -> None:  # noqa: ANN401 - any LlmClient
        self._inner = inner
        self._directory = directory

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        result: LlmResult[T] = await self._inner.generate_structured(request)
        self._directory.mkdir(parents=True, exist_ok=True)
        recording = {
            "prompt_ref": request.prompt_ref,
            "schema": request.schema.__name__,
            "call": result.call.model_dump(exclude={"replayed"}),
            "output": result.output.model_dump(mode="json"),
        }
        path = self._directory / f"{cache_key(request)}.json"
        path.write_text(
            json.dumps(recording, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        return result
