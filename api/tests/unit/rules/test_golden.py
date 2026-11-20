"""Golden cases A, B and C from docs/BUILD_PLAN.md §1.4. These numbers are on stage; they
must never drift. The facts live in demo_cases/ so the CLI, the demo and these tests agree."""

import pytest

from arzi.domain.enums import CitationStatus, ClaimMode, FlagKind
from arzi.domain.money import Paise, to_paise
from arzi.rules.context import POLICY_REF_PREFIX
from arzi.rules.reference import citations
from arzi.rules.registry import RULES
from tests.unit.rules.helpers import audit_case as _audit
from tests.unit.rules.helpers import line_cut, only, rule_ids


def inr(text: str) -> Paise:
    return to_paise(text)


def test_case_a_pre_submission_audit() -> None:
    result = _audit("case_a")
    t = result.totals

    assert result.mode is ClaimMode.PRE_SUBMISSION
    assert t.billed == inr("₹2,25,500")
    assert t.predicted_payable == inr("₹1,57,612.50")
    assert t.at_risk == inr("₹67,887.50")
    assert t.recoverable_on_appeal == 0
    assert result.fix_savings == inr("₹46,875")
    assert [(f.rule_id, f.amount_at_risk) for f in result.flags] == [
        ("NON_PAYABLE", inr("₹3,500")),
        ("ROOM_RENT_EXCESS", inr("₹12,000")),
        ("PROP_ROOM_RENT", inr("₹34,875")),
        ("COPAY", inr("₹17,512.50")),
    ]
    admissible = sum(o.admissible for o in result.lines)
    assert admissible == inr("₹1,75,125")
    # ICU, pharmacy, diagnostics and implant lines carry no flag and no cut.
    flagged_lines = {i for f in result.flags if f.rule_id != "COPAY" for i in f.lines}
    assert flagged_lines.isdisjoint({2, 6, 7, 8})
    assert all(o.admissible == o.billed for o in result.lines if o.line_id in {2, 6, 7, 8})
    assert only(result, "ROOM_RENT_EXCESS").fix_savings == inr("₹46,875")
    trace = {s.formula for s in result.trace}
    assert "₹93,000 associated expenses × ₹5,000 / ₹8,000 = ₹58,125" in trace


def test_case_b_deduction_appeal() -> None:
    result = _audit("case_b")
    t = result.totals

    assert t.predicted_payable == inr("₹1,58,512.50")
    assert t.recoverable_on_appeal == inr("₹20,137.50")
    wrong = only(result, "PROP_WRONGLY_APPLIED")
    assert wrong.amount_at_risk == inr("₹21,375")
    assert wrong.recoverable == inr("₹19,237.50")
    assert wrong.lines == (2, 6, 7)
    subsumed = only(result, "SUBSUMED_ITEM")
    assert subsumed.recoverable == inr("₹900")
    assert citations()[subsumed.citation_refs[0]].status is CitationStatus.VERIFY
    assert {f.rule_id for f in result.flags if f.kind is FlagKind.DISPUTE} == {
        "PROP_WRONGLY_APPLIED",
        "SUBSUMED_ITEM",
    }
    assert result.fix_savings == 0  # the patient has gone home; no room fix is possible
    comparison = result.trace[-1]
    assert comparison.rule_id == "INSURER_COMPARISON"
    assert comparison.result == inr("₹20,137.50")  # engine payable - insurer approved ₹1,38,375


def test_case_c_rejection_appeal() -> None:
    result = _audit("case_c")

    assert rule_ids(result) == ["WAITING_REJECTION_INVALID"]
    flag = only(result, "WAITING_REJECTION_INVALID")
    assert flag.appealable
    assert flag.kind is FlagKind.DISPUTE
    assert flag.recoverable == result.totals.predicted_payable == inr("₹3,10,000")
    assert flag.citation_refs == ("IRDAI_PED_36M", "policy:5.2")
    assert result.totals.recoverable_on_appeal == inr("₹3,10,000")


@pytest.mark.parametrize("case", ["case_a", "case_b", "case_c"])
def test_demo_cases_are_deterministic(case: str) -> None:
    assert _audit(case) == _audit(case)


def test_case_b_line_level_cuts() -> None:
    result = _audit("case_b")
    assert line_cut(result, 3, "PROP_ROOM_RENT") == inr("₹22,500")
    assert line_cut(result, 6, "PROP_ROOM_RENT") == 0
    assert line_cut(result, 12, "NON_PAYABLE") == 0


def test_flags_cite_only_what_their_rule_allows_and_link_to_the_trace() -> None:
    specs = {spec.rule_id: spec for spec in RULES}
    for case in ("case_a", "case_b", "case_c"):
        result = _audit(case)
        step_ids = {s.step_id for s in result.trace}
        for flag in result.flags:
            spec = specs[flag.rule_id]
            for ref in flag.citation_refs:
                is_policy = ref.startswith(POLICY_REF_PREFIX)
                assert (is_policy and spec.cites_policy) or ref in spec.citation_ids, ref
            assert flag.trace_ref in step_ids
