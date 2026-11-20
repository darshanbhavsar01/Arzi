"""The guarded reasoning node under ADK: pass, retry with feedback, needs review, unavailable."""

import datetime as dt
import json
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import BaseModel

from arzi.adapters.demo_seed import DEMO_HOSPITAL
from arzi.agents import flag_explainer, policy_interpreter
from arzi.agents.bridge import extract_input, instruction
from arzi.agents.guardrails import FEEDBACK_HEADER, Violation, validate_amounts
from arzi.agents.nodes import ModelSettings, ReasoningTask
from arzi.agents.pipeline import run_reasoning
from arzi.domain.enums import PolicyTermKind, ReasoningStatus
from arzi.domain.models import ClaimFacts, ClaimRecord, LlmCall
from arzi.prompts import Prompt
from arzi.rules.engine import audit
from arzi.services.pipeline import RunContext, Summary
from arzi.services.ports import LlmRequest, LlmResult, LlmUnavailableError
from arzi.services.reconcile import ReconcileOutcome
from tests.unit.rules.helpers import DEMO_CASES

PROMPT = Prompt(name="test_note", version=1, text="Write a note.")


class Note(BaseModel):
    text: str


class Scripted:
    """Answers (or failures) in order; remembers every request."""

    def __init__(self, *answers: dict[str, Any] | Exception) -> None:
        self._answers = list(answers)
        self.requests: list[LlmRequest[Any]] = []

    async def generate_structured[T: BaseModel](self, request: LlmRequest[T]) -> LlmResult[T]:
        self.requests.append(request)
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        call = LlmCall(
            prompt_ref=request.prompt_ref, model=request.model, input_tokens=11, output_tokens=7
        )
        return LlmResult(output=request.schema.model_validate(answer), call=call)


class Outcome:
    def __init__(self) -> None:
        self.output: BaseModel | None = None
        self.status: ReasoningStatus | None = None
        self.violations: Sequence[Violation] = ()

    def finish(
        self, output: BaseModel | None, status: ReasoningStatus, violations: Sequence[Violation]
    ) -> Summary:
        self.output, self.status, self.violations = output, status, violations
        return {"status": str(status)}


def _task(outcome: Outcome, payload: dict[str, Any] | None = None) -> ReasoningTask[Note]:
    return ReasoningTask(
        name="note",
        prompt=PROMPT,
        schema=Note,
        build_input=lambda: payload,
        check=lambda note: validate_amounts(note.text, "text"),
        finish=outcome.finish,
    )


async def _run(client: Scripted, task: ReasoningTask[Any]) -> list[LlmCall]:
    calls: list[LlmCall] = []
    await run_reasoning(task, ModelSettings(client=client, model="flash-test"), calls)
    return calls


async def test_a_compliant_answer_passes_first_time_and_is_recorded() -> None:
    client, outcome = Scripted({"text": "{{totals.at_risk}} is at risk."}), Outcome()
    calls = await _run(client, _task(outcome, {"flag": "ROOM"}))

    assert outcome.status is ReasoningStatus.PASSED
    assert outcome.output == Note(text="{{totals.at_risk}} is at risk.")
    (request,) = client.requests
    # Only the versioned prompt and the marked input reach the model, never ADK's own lines.
    assert request.system == PROMPT.text
    assert json.loads(request.text) == {"flag": "ROOM"}
    assert request.prompt_ref == "test_note@v1"
    assert request.model == "flash-test"
    assert [(c.prompt_ref, c.input_tokens) for c in calls] == [("test_note@v1", 11)]


async def test_a_violation_is_retried_once_with_the_validator_feedback() -> None:
    client = Scripted({"text": "₹900 is at risk."}, {"text": "{{totals.at_risk}} is at risk."})
    outcome = Outcome()
    calls = await _run(client, _task(outcome, {"flag": "ROOM"}))

    assert outcome.status is ReasoningStatus.RETRIED
    assert outcome.violations == ()
    first, second = client.requests
    assert FEEDBACK_HEADER not in first.text
    assert FEEDBACK_HEADER in second.text
    assert "`text`" in second.text
    assert len(calls) == 2


async def test_a_second_violation_keeps_the_draft_for_review() -> None:
    client = Scripted({"text": "₹900"}, {"text": "Rs. 900"})
    outcome = Outcome()
    await _run(client, _task(outcome, {"flag": "ROOM"}))

    assert outcome.status is ReasoningStatus.NEEDS_REVIEW
    assert outcome.output == Note(text="Rs. 900")
    assert outcome.violations == (Violation("stray_amount", "text"),)


async def test_an_unavailable_model_leaves_the_step_unavailable() -> None:
    client, outcome = Scripted(LlmUnavailableError("replay-miss")), Outcome()
    await _run(client, _task(outcome, {"flag": "ROOM"}))
    assert outcome.status is ReasoningStatus.UNAVAILABLE
    assert outcome.output is None


async def test_nothing_to_reason_about_skips_the_model() -> None:
    client, outcome = Scripted(), Outcome()
    await _run(client, _task(outcome, None))
    assert outcome.status is ReasoningStatus.SKIPPED
    assert client.requests == []


def test_the_input_block_is_required() -> None:
    assert extract_input(instruction(PROMPT, '{"a": 1}') + "\n\nYou are an agent.") == '{"a": 1}'
    with pytest.raises(ValueError, match="no arzi input"):
        extract_input("Write a note.")


# --------------------------------------------------------------------------- policy interpreter


def _context(case: str) -> RunContext:
    facts = ClaimFacts.model_validate_json((DEMO_CASES / case / "facts.json").read_bytes())
    claim = ClaimRecord(
        hospital_id="h", claim_id=facts.claim_id, created_at=dt.datetime(2026, 1, 1)
    )
    ctx = RunContext(claim=claim, hospital=DEMO_HOSPITAL, documents=())
    ctx.reconciled = ReconcileOutcome(facts=facts)
    return ctx


def _term(term: str, clause: str | None, confidence: float = 0.95) -> dict[str, Any]:
    return {
        "term": term,
        "clause_id": clause,
        "summary": "Room rent is payable up to {{policy.room_rent_cap}} a day.",
        "confidence": confidence,
    }


async def test_policy_reading_that_disagrees_with_extraction_needs_confirmation() -> None:
    ctx = _context("case_b")
    client = Scripted(
        {
            "terms": [
                _term("room_rent_cap", "4.2"),
                _term("proportionate_deduction", "4.2"),  # extraction used 4.3
                _term("copay", "7.4", confidence=0.6),
            ],
            "citations": ["policy:4.2"],
        }
    )
    await _run(client, policy_interpreter.task(ctx))

    review = ctx.policy_review
    assert review is not None
    assert review.status is ReasoningStatus.PASSED
    assert review.prompt_ref == "interpret_policy@v1"
    flags = {t.term: t.needs_confirmation for t in review.terms}
    assert flags == {
        PolicyTermKind.ROOM_RENT_CAP: False,
        PolicyTermKind.PROPORTIONATE_DEDUCTION: True,
        PolicyTermKind.COPAY: True,
    }
    assert review.terms[0].summary.text == "Room rent is payable up to ₹5,000 a day."
    (issue,) = ctx.review_issues
    assert issue.code == "policy_term_unconfirmed"
    assert "clause 4.2" in issue.message
    assert "4.3" in issue.message
    request = json.loads(client.requests[0].text)
    assert request["extracted"]["proportionate_deduction"] == ["4.3"]
    assert "policy:4.3" in request["allowed_refs"]


async def test_policy_reading_with_an_unknown_clause_is_retried() -> None:
    ctx = _context("case_b")
    bad = {"terms": [_term("room_rent_cap", "12.9")], "citations": ["policy:12.9"]}
    good = {"terms": [_term("room_rent_cap", "4.2")], "citations": ["policy:4.2"]}
    await _run(Scripted(bad, good), policy_interpreter.task(ctx))
    assert ctx.policy_review is not None
    assert ctx.policy_review.status is ReasoningStatus.RETRIED


async def test_policy_reading_is_skipped_without_clauses() -> None:
    ctx = _context("case_b")
    assert ctx.reconciled is not None
    bare = ctx.reconciled.facts.policy.model_copy(
        update={
            "clauses": (),
            "room_rent_cap": None,
            "proportionate_clause_id": None,
            "copay": None,
            "specific_waiting": (),
            "sub_limits": (),
            "claims_clause_id": None,
        }
    )
    ctx.reconciled = ReconcileOutcome(
        facts=ctx.reconciled.facts.model_copy(update={"policy": bare})
    )
    client = Scripted()
    await _run(client, policy_interpreter.task(ctx))
    assert client.requests == []
    assert ctx.policy_review is not None
    assert ctx.policy_review.status is ReasoningStatus.SKIPPED
    assert ctx.policy_review.prompt_ref is None


# --------------------------------------------------------------------------- flag explainer


def test_explanations_must_cover_every_flag_exactly_once() -> None:
    check = flag_explainer.check_coverage
    assert check(["A", "B"], ["A", "B"]) == []
    assert check(["A"], ["A", "B"]) == [Violation("missing_flag", "items")]
    assert check(["A", "B", "C"], ["A", "B"]) == [Violation("unexpected_flag", "items")]
    assert check(["A", "A", "B"], ["A", "B"]) == [Violation("unexpected_flag", "items")]


async def test_explanations_that_needs_review_keep_unrendered_text_hidden() -> None:
    ctx = _context("case_c")
    assert ctx.reconciled is not None
    ctx.audit = audit(ctx.reconciled.facts)
    flag_id = ctx.audit.flags[0].flag_id
    item = {
        "flag_id": flag_id,
        "headline": "Rejection is invalid",
        "explanation": "Pay {{flag.INVENTED.amount}} now.",
        "fix": "File an appeal.",
        "citations": ["IRDAI_PED_36M"],
    }
    await _run(Scripted({"items": [item]}, {"items": [item]}), flag_explainer.task(ctx))
    narratives = ctx.narratives
    assert narratives is not None
    assert narratives.status is ReasoningStatus.NEEDS_REVIEW
    assert narratives.violations == ("unknown_placeholder in items[0].explanation",)
    (narrative,) = narratives.items
    assert narrative.explanation.text is None  # never shown as if it were checked
    assert narrative.fix.text == "File an appeal."
