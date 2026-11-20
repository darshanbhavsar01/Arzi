"""``fake`` LLM mode for the reasoning agents: deterministic answers built from their own input.

Document calls still go to the extraction fixtures; reasoning calls get a plain, guardrail-
compliant answer derived from the input (every flag covered, citations from the input, money only
as placeholders). Local development and tests therefore run the whole ADK pipeline offline.
"""

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel

from arzi.agents.guardrails import FEEDBACK_HEADER
from arzi.agents.schemas import AppealDraftOutput, FlagNarrativesDraft, PolicyTermsDraft
from arzi.domain.models import LlmCall
from arzi.services.ports import LlmClient, LlmRequest, LlmResult, LlmUnavailableError

Payload = dict[str, Any]


def _policy_terms(payload: Payload) -> Payload:
    terms = [
        {
            "term": term,
            "clause_id": ids[0],
            "summary": f"Clause {ids[0]} sets this term.",
            "confidence": 1.0,
        }
        for term, ids in sorted(payload["extracted"].items())
    ]
    return {"terms": terms, "citations": [f"policy:{t['clause_id']}" for t in terms]}


def _narratives(payload: Payload) -> Payload:
    items = []
    for flag in payload["flags"]:
        money = "recoverable" if flag["kind"] == "dispute" else "amount"
        placeholder = f"{{{{flag.{flag['flag_id']}.{money}}}}}"
        items.append(
            {
                "flag_id": flag["flag_id"],
                "headline": flag["rule_id"].replace("_", " ").capitalize(),
                "explanation": f"The audit rules flag this item: {placeholder}.",
                "fix": "Review the affected lines and take the suggested next step.",
                "citations": flag["citations"],
            }
        )
    return {"items": items}


def _appeal(payload: Payload) -> Payload:
    items = [
        {
            "flag_id": item["flag_id"],
            "argument": "The insurer's decision on this item does not follow the cited rules.",
            "citations": item["citations"],
        }
        for item in payload["disputed"]
    ]
    return {
        "subject": "Request to review the claim decision",
        "facts": "The patient was treated at the hospital and the insurer decided the claim as "
        "set out in its letter.",
        "items": items,
        "relief": "We request that the insurer pay {{totals.recoverable}}.",
        "citations": sorted({c for item in items for c in item["citations"]}),
    }


_BUILDERS: dict[type[BaseModel], Callable[[Payload], Payload]] = {
    PolicyTermsDraft: _policy_terms,
    FlagNarrativesDraft: _narratives,
    AppealDraftOutput: _appeal,
}


class StubReasoner:
    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        build = _BUILDERS.get(request.schema)
        if build is None:
            raise LlmUnavailableError("fixture-miss")
        payload = json.loads(request.text.split(FEEDBACK_HEADER, 1)[0])
        output = request.schema.model_validate(build(payload))
        call = LlmCall(prompt_ref=request.prompt_ref, model=request.model, replayed=True)
        return LlmResult(output=output, call=call)


class FakeLlmClient:
    """Routes document calls to the extraction fixtures and reasoning calls to the stubs."""

    def __init__(self, documents: LlmClient, reasoning: LlmClient | None = None) -> None:
        self._documents = documents
        self._reasoning = reasoning or StubReasoner()

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        target = self._documents if request.files else self._reasoning
        return await target.generate_structured(request)
