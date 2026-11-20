"""``fake`` LLM mode: the ideal extraction of each synthetic demo document.

``make demo-cases`` writes ``demo_cases/*/extraction/<file>.json`` describing what a perfect
transcription of each document looks like. This client serves those by the file's SHA-256, so
local development and tests run the whole pipeline deterministically and for free. Any other
file is a clear miss, never a made-up answer.
"""

import json
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from arzi.domain.models import LlmCall
from arzi.services.extraction_schemas import Classification
from arzi.services.ports import LlmRequest, LlmResult, LlmUnavailableError


class FixtureLlmClient:
    def __init__(self, root: Path) -> None:
        self._root = root

    @cached_property
    def _fixtures(self) -> dict[str, dict[str, Any]]:
        fixtures: dict[str, dict[str, Any]] = {}
        for path in sorted(self._root.glob("*/extraction/*.json")):
            entry = json.loads(path.read_text(encoding="utf-8"))
            fixtures[entry["sha256"]] = entry
        return fixtures

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        if len(request.files) != 1 or request.files[0].sha256 not in self._fixtures:
            raise LlmUnavailableError("fixture-miss")
        entry = self._fixtures[request.files[0].sha256]
        if request.schema is Classification:
            payload: Any = {"document_type": entry["document_type"], "confidence": 1.0}
        elif entry["extraction"] is None:
            raise LlmUnavailableError("fixture-miss")
        else:
            payload = entry["extraction"]
        call = LlmCall(prompt_ref=request.prompt_ref, model=request.model, replayed=True)
        return LlmResult(output=request.schema.model_validate(payload), call=call)
