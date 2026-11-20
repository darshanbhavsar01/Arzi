import json
from typing import Any

from arzi.agents import appeal_drafter
from arzi.agents.appeal_drafter import AppealJob, disputed, insurer_reason
from arzi.agents.guardrails import Violation
from arzi.agents.schemas import AppealDraftOutput
from arzi.domain.enums import AppealForum, RejectionGround
from arzi.domain.models import ClaimFacts
from arzi.rules.engine import audit
from tests.unit.rules.helpers import DEMO_CASES


def _job(case: str, forum: AppealForum = AppealForum.INSURER_GRO) -> AppealJob:
    facts = ClaimFacts.model_validate_json((DEMO_CASES / case / "facts.json").read_bytes())
    return AppealJob(facts=facts, audit=audit(facts), forum=forum)


def _answer(job: AppealJob, **overrides: Any) -> AppealDraftOutput:  # noqa: ANN401
    items = [
        {"flag_id": f.flag_id, "argument": "The cut is wrong.", "citations": list(f.citation_refs)}
        for f in disputed(job.audit)
    ]
    body = {
        "subject": "Review request",
        "facts": "Admitted and treated.",
        "items": items,
        "relief": "Please pay {{ totals.recoverable }}.",
        "citations": [],
    }
    return AppealDraftOutput.model_validate(body | overrides)


def test_the_input_lists_the_disputed_items_and_the_forum_rules() -> None:
    job = _job("case_b")
    payload = appeal_drafter.task(job).build_input()
    assert payload is not None
    json.dumps(payload)  # the input is plain JSON
    assert [d["flag_id"] for d in payload["disputed"]] == ["SUBSUMED_ITEM", "PROP_WRONGLY_APPLIED"]
    assert payload["disputed"][1]["amount_placeholder"] == "flag.PROP_WRONGLY_APPLIED.recoverable"
    assert "INSURER_GRIEVANCE_15D" in payload["allowed_refs"]
    assert "OMBUDSMAN_RULES_2017" not in payload["allowed_refs"]
    assert "totals.recoverable" in payload["placeholders"]


def test_nothing_disputed_skips_the_drafter() -> None:
    assert appeal_drafter.task(_job("case_a")).build_input() is None


def test_a_compliant_draft_passes() -> None:
    job = _job("case_b")
    assert appeal_drafter.task(job).check(_answer(job)) == []


def test_relief_must_carry_the_relief_placeholder() -> None:
    job = _job("case_b")
    found = appeal_drafter.task(job).check(_answer(job, relief="Please pay what is due."))
    assert found == [Violation("missing_relief", "relief")]


def test_insurer_reasons_are_fixed_wording() -> None:
    job = _job("case_c")
    (flag,) = disputed(job.audit)
    assert (
        insurer_reason(flag, job.facts) == "Rejected under the pre-existing disease waiting period"
    )
    letter = job.facts.insurer_letter
    assert letter is not None
    other = letter.model_copy(update={"rejection_ground": RejectionGround.OTHER})
    facts = job.facts.model_copy(update={"insurer_letter": other})
    assert insurer_reason(flag, facts) == "As stated in the insurer's letter"
