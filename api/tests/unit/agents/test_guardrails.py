"""Adversarial tests for the amount guard, the citation whitelist and placeholder rendering."""

import pytest

from arzi.agents.guardrails import (
    FEEDBACK_HEADER,
    GuardrailError,
    ProsePolicy,
    UnknownPlaceholderError,
    Violation,
    allowed_refs,
    check_prose,
    feedback,
    placeholder_values,
    render,
    try_render,
    validate_amounts,
    validate_citations,
)
from arzi.domain.models import ClaimFacts
from arzi.domain.money import rupees
from tests.unit.rules.helpers import DEMO_CASES, audit_case


def _facts(case: str) -> ClaimFacts:
    return ClaimFacts.model_validate_json((DEMO_CASES / case / "facts.json").read_bytes())


@pytest.mark.parametrize(
    "text",
    [
        "The insurer cut ₹20,137.50 too much.",
        "Rs. 900 was deducted for registration.",
        "Rs900 deducted",
        "INR 5000 is recoverable.",
        "a refund of 20,137 rupees",
        "pay 900/- to the hospital",
        "1,57,612.50 is payable",
        "157,612 is payable",
        "the claim is under 50 lakh",
        "up to 2 crore",
        # Hindi: amount in words with digits, the abbreviation, native digits
        "बीमा कंपनी ने 2 लाख रुपये काटे",
        "कुल रु. 900 की कटौती",
        "₹५०० वापस मिलेंगे",
        # Gujarati
        "૫૦૦ રૂપિયા પાછા મળશે",
        "રૂ. 900 કપાયા",
        "50 લાખ સુધી",
    ],
)
def test_amount_guard_rejects_written_amounts(text: str) -> None:
    assert validate_amounts(text, "explanation") == [Violation("stray_amount", "explanation")]


@pytest.mark.parametrize(
    "text",
    [
        "{{flag.PROP_ROOM_RENT.amount}} is at risk on lines 3, 4 and 5.",
        "Cover ran for 40 months against a 36-month maximum.",
        "The policy has a 10% co-payment under clause 7.4.",
        "Lines 12,13 were affected.",
        "Admitted on 2026-03-14 and discharged on 14/03/2026.",
        "रोगी 40 महीने से कवर है।",
    ],
)
def test_amount_guard_allows_other_numbers_and_placeholders(text: str) -> None:
    assert validate_amounts(text, "explanation") == []


def test_currency_sign_before_a_placeholder_is_rejected() -> None:
    assert validate_amounts("Pay ₹{{totals.recoverable}} now.", "relief") == [
        Violation("currency_before_placeholder", "relief")
    ]


@pytest.fixture
def policy_b() -> ProsePolicy:
    facts = _facts("case_b")
    result = audit_case("case_b")
    refs = allowed_refs(facts, (r for f in result.flags for r in f.citation_refs))
    return ProsePolicy(refs, frozenset(placeholder_values(facts, result)))


def test_allowed_refs_are_flag_citations_and_policy_clauses_only(policy_b: ProsePolicy) -> None:
    assert {
        "IRDAI_PROP_DED_2020",
        "IRDAI_NON_PAYABLE_ANNEX_I",
        "policy:4.3",
    } <= policy_b.allowed_refs
    assert "IRDAI_PED_36M" not in policy_b.allowed_refs  # no case B flag cites it
    extra = allowed_refs(_facts("case_b"), ("IRDAI_MADE_UP", "policy:99.9", "BIMA_BHAROSA"))
    assert "BIMA_BHAROSA" in extra
    assert not {"IRDAI_MADE_UP", "policy:99.9"} & extra


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("As per circular IRDAI/HLT/CIR/999/2023 this is wrong.", "unknown_regulation"),
        ("Under circular no. 45 of 2021 the cut is invalid.", "unknown_regulation"),
        ("Clause 9.9 of the policy covers it.", "unknown_clause"),
        ("See paragraph 7 of the Master Circular.", "paragraph_reference"),
        ("Recover {{flag.MADE_UP.amount}}.", "unknown_placeholder"),
        ("It is ₹900.", "stray_amount"),
    ],
)
def test_prose_check_rejects_invented_references(
    policy_b: ProsePolicy, text: str, code: str
) -> None:
    assert [v.code for v in check_prose(text, policy_b, "argument")] == [code]


def test_prose_check_accepts_references_in_context(policy_b: ProsePolicy) -> None:
    text = (
        "Circular IRDAI/HLT/REG/CIR/151/06/2020 excludes pharmacy from proportionate deduction, "
        "and clause 4.3 of the policy says the same, so {{flag.PROP_WRONGLY_APPLIED.recoverable}} "
        "should be paid."
    )
    assert check_prose(text, policy_b, "argument") == []


def test_citation_whitelist() -> None:
    allowed = frozenset({"IRDAI_PED_36M", "policy:5.1"})
    assert validate_citations(["IRDAI_PED_36M", "policy:5.1"], allowed, "items[0]") == []
    assert validate_citations(["IRDAI_PED_36M", "IRDAI_INVENTED"], allowed, "items[0]") == [
        Violation("unknown_citation", "items[0]")
    ]


def test_render_fills_engine_amounts_in_en_in_format() -> None:
    values = placeholder_values(_facts("case_b"), audit_case("case_b"))
    text = render("Recover {{totals.recoverable}} ({{ flag.SUBSUMED_ITEM.recoverable }}).", values)
    assert text == "Recover ₹20,137.50 (₹900)."
    assert values["letter.approved"] == rupees(1_38_375)
    assert values["policy.room_rent_cap"] == rupees(5_000)


def test_render_keeps_latin_digits_unless_native_digits_are_asked_for() -> None:
    values = {"totals.recoverable": rupees(3_10_000)}
    assert render("{{totals.recoverable}}", values, locale="gu") == "₹3,10,000"
    shown = render("{{totals.recoverable}}", values, locale="gu", native_digits=True)
    assert shown == "₹૩,૧૦,૦૦૦"  # noqa: RUF001 - native digits on purpose
    shown = render("{{totals.recoverable}}", values, locale="hi", native_digits=True)
    assert shown == "₹३,१०,०००"  # noqa: RUF001 - native digits on purpose
    assert render("{{totals.recoverable}}", values, locale="en", native_digits=True) == "₹3,10,000"


def test_unknown_placeholders_never_render() -> None:
    with pytest.raises(UnknownPlaceholderError):
        render("{{totals.invented}}", {})
    assert try_render("{{totals.invented}}", {}) is None
    assert try_render("no money here", {}) == "no money here"


def test_placeholders_before_the_audit_cover_policy_amounts_only() -> None:
    values = placeholder_values(_facts("case_c"))
    assert "policy.sum_insured" in values
    assert not any(name.startswith(("totals.", "flag.")) for name in values)


def test_feedback_names_the_rule_and_the_field_but_not_the_text() -> None:
    note = feedback([Violation("stray_amount", "items[1].argument")])
    assert note.startswith(FEEDBACK_HEADER)
    assert "items[1].argument" in note
    assert "placeholders" in note


def test_guardrail_error_lists_violations() -> None:
    error = GuardrailError([Violation("stray_amount", "facts")])
    assert str(error) == "stray_amount in facts"
    assert error.violations == (Violation("stray_amount", "facts"),)


@pytest.mark.parametrize(
    ("template", "shown"),
    [
        (
            'Under "Norms on proportionate deductions" (IRDAI_PROP_DED_2020), ICU is excluded.',
            'Under "Norms on proportionate deductions", ICU is excluded.',
        ),
        ("Policy clause 4.3 (policy:4.3) agrees.", "Policy clause 4.3 (clause 4.3) agrees."),
        ("See policy:5.1.", "See clause 5.1."),
        (
            "IRDAI_PED_36M caps it.",
            "Pre-existing disease: look-back and maximum waiting period caps it.",
        ),
        ("(see IRDAI_PED_36M)", "(see Pre-existing disease: look-back and maximum waiting period)"),
        ("PROP_ROOM_RENT and NOT_A_REF stay.", "PROP_ROOM_RENT and NOT_A_REF stay."),
    ],
)
def test_rendering_makes_reference_ids_readable(template: str, shown: str) -> None:
    assert render(template, {}) == shown
