from typing import Any

import pytest

from arzi.agents import family_explainer
from arzi.agents.family_explainer import HUMAN_REVIEW, FamilyJob
from arzi.agents.guardrails import Violation
from arzi.agents.schemas import FamilyExplanationDraft
from arzi.domain.enums import ReasoningStatus
from arzi.domain.models import ClaimFacts, Language
from arzi.rules.engine import audit
from tests.unit.rules.helpers import DEMO_CASES


def _job(lang: Language = "gu") -> FamilyJob:
    facts = ClaimFacts.model_validate_json((DEMO_CASES / "case_c" / "facts.json").read_bytes())
    return FamilyJob(facts=facts, audit=audit(facts), lang=lang)


def _draft(**overrides: Any) -> FamilyExplanationDraft:  # noqa: ANN401
    body: dict[str, Any] = {
        "headline": "નિર્ણયને પડકારી શકાય છે.",
        "what_happened": ["વીમા કંપનીએ {{totals.recoverable}} નો દાવો નકાર્યો."],
        "why": ["રાહ જોવાનો સમય પૂરો થઈ ગયો હતો."],
        "next_steps": ["હોસ્પિટલ ડેસ્ક અરજી તૈયાર કરશે."],
        "reassurance": "તમારા કેસ પર ધ્યાન અપાય છે.",
        "citations": ["IRDAI_PED_36M"],
    }
    return FamilyExplanationDraft.model_validate(body | overrides)


def test_the_input_carries_the_language_and_its_glossary() -> None:
    payload = family_explainer.task(_job("hi")).build_input()
    assert payload is not None
    assert payload["lang"] == "hi"
    assert payload["glossary"]["insurer"] == "बीमा कंपनी"
    assert "totals.recoverable" in payload["placeholders"]


def test_a_plain_compliant_explanation_passes() -> None:
    assert family_explainer.task(_job()).check(_draft()) == []


@pytest.mark.parametrize(
    ("field", "text"),
    [
        ("headline", "આપણે આ નિર્ણય ચોક્કસ બદલાવી શકીશું."),
        ("reassurance", "पैसा ज़रूर वापस मिलेगा।"),
        ("headline", "The rejection will be reversed."),
    ],
)
def test_promising_an_outcome_is_rejected(field: str, text: str) -> None:
    found = family_explainer.task(_job()).check(_draft(**{field: text}))
    assert Violation("outcome_promise", field) in found


@pytest.mark.parametrize(
    "text",
    [
        "જરૂર પડે તો હોસ્પિટલના ડેસ્કનો સંપર્ક કરો.",
        "દાવા માટે જરૂરી દસ્તાવેજો જોડો.",
        "अगर ज़रूरत हो तो अस्पताल डेस्क से बात कीजिए।",
        "ચોક્કસ સમયમાં અરજી મોકલો.",
    ],
)
def test_need_and_specific_are_not_read_as_promises(text: str) -> None:
    assert family_explainer.task(_job()).check(_draft(headline=text)) == []


@pytest.mark.parametrize(
    "sentence",
    [
        "વીમા કંપનીએ \u0ae9,\u0ae7\u0ae6,\u0ae6\u0ae6\u0ae6 રૂપિયા નકાર્યા.",  # Gujarati digits
        "बीमा कंपनी ने 3 लाख रुपये नहीं दिए।",
        "રૂ. 900 કપાયા.",
    ],
)
def test_written_amounts_are_rejected_in_gujarati_and_hindi(sentence: str) -> None:
    found = family_explainer.task(_job()).check(_draft(what_happened=[sentence]))
    assert Violation("stray_amount", "what_happened[0]") in found


def test_the_human_review_note_is_added_once_in_fixed_words() -> None:
    job = _job()
    family_explainer.task(job).finish(_draft(), ReasoningStatus.PASSED, ())
    assert job.result is not None
    assert job.result.reassurance.text == f"તમારા કેસ પર ધ્યાન અપાય છે. {HUMAN_REVIEW['gu']}"
    assert job.result.what_happened[0].text == "વીમા કંપનીએ ₹3,10,000 નો દાવો નકાર્યો."

    again = _job()
    family_explainer.task(again).finish(
        _draft(reassurance=HUMAN_REVIEW["gu"]), ReasoningStatus.PASSED, ()
    )
    assert again.result is not None
    assert again.result.reassurance.text == HUMAN_REVIEW["gu"]


def test_an_unavailable_model_still_leaves_the_fixed_note() -> None:
    job = _job("en")
    family_explainer.task(job).finish(None, ReasoningStatus.UNAVAILABLE, ())
    assert job.result is not None
    assert job.result.status is ReasoningStatus.UNAVAILABLE
    assert job.result.reassurance.text == HUMAN_REVIEW["en"]
