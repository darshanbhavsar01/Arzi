from decimal import Decimal

import pytest

from arzi.domain.enums import (
    ClaimMode,
    CopayBase,
    DeductionReason,
    DocumentKind,
    InsurerLetterType,
    LineCategory,
    RoomRentCapType,
    Severity,
)
from arzi.domain.models import Copay, InsurerDeduction, InsurerLetter, PerDayAmountCap
from arzi.domain.money import rupees
from arzi.rules.engine import audit
from tests.builders import ALL_DOCUMENTS, facts, line, policy
from tests.unit.rules.helpers import only, rule_ids

C = LineCategory
D = DocumentKind


def _prorated(*line_ids: int, amount: int = 1_000) -> InsurerLetter:
    deductions = [
        InsurerDeduction(line_id=i, amount=rupees(amount), reason=DeductionReason.PROPORTIONATE)
        for i in line_ids
    ]
    deductions.append(
        InsurerDeduction(line_id=None, amount=rupees(50), reason=DeductionReason.PROPORTIONATE)
    )
    return InsurerLetter(
        type=InsurerLetterType.DEDUCTION,
        amount_claimed=rupees(20_000),
        amount_approved=rupees(17_000),
        deductions=tuple(deductions),
    )


def test_prorating_with_the_room_within_cap_is_recoverable_in_full() -> None:
    result = audit(
        facts(
            line(1, C.SURGEON, 10_000),
            line(2, C.PHARMACY, 10_000),
            line(3, C.OTHER, 500),
            mode=ClaimMode.POST_DEDUCTION,
            letter=_prorated(1, 2, 3, amount=1_000),
            policy_=policy(copay=Copay(pct=Decimal(10), base=CopayBase.CLAIMED)),
        )
    )
    flag = only(result, "PROP_WRONGLY_APPLIED")
    assert flag.lines == (1, 2, 3)
    assert flag.amount_at_risk == rupees(2_500)  # line 3 capped at its billed ₹500
    assert flag.recoverable == rupees(2_500)  # co-pay on claimed is unaffected by recovery
    # engine payable 20,500 - 2,050 co-pay = 18,450 vs approved 17,000
    assert result.trace[-1].rule_id == "INSURER_COMPARISON"
    assert result.trace[-1].result == rupees(1_450)


def test_only_lines_the_engine_does_not_prorate_are_disputed() -> None:
    cap = PerDayAmountCap(type=RoomRentCapType.PER_DAY_AMOUNT, amount=rupees(5_000))
    result = audit(
        facts(
            line(1, C.ROOM, 8_000),
            line(2, C.SURGEON, 8_000),
            line(3, C.PHARMACY, 8_000),
            mode=ClaimMode.POST_DEDUCTION,
            letter=_prorated(2, 3, amount=3_000),
            policy_=policy(room_rent_cap=cap),
        )
    )
    flag = only(result, "PROP_WRONGLY_APPLIED")
    assert flag.lines == (3,)
    assert flag.recoverable == rupees(3_000)


def test_no_proportionate_cuts_means_no_dispute() -> None:
    letter = InsurerLetter(type=InsurerLetterType.DEDUCTION, amount_claimed=rupees(1))
    result = audit(facts(line(1, C.PHARMACY, 100), mode=ClaimMode.POST_DEDUCTION, letter=letter))
    assert rule_ids(result) == []


@pytest.mark.parametrize(
    ("present", "expected"),
    [
        (ALL_DOCUMENTS, []),
        (
            (),
            [
                ("DOC_MISSING-discharge_summary", Severity.HIGH, 70_000, ()),
                ("DOC_MISSING-investigation_reports", Severity.MEDIUM, 10_000, (2,)),
                ("DOC_MISSING-implant_invoice", Severity.HIGH, 40_000, (3,)),
            ],
        ),
        (
            (D.DISCHARGE_SUMMARY, D.INVESTIGATION_REPORTS),
            [("DOC_MISSING-implant_invoice", Severity.HIGH, 40_000, (3,))],
        ),
    ],
)
def test_required_documents(
    present: tuple[DocumentKind, ...], expected: list[tuple[str, Severity, int, tuple[int, ...]]]
) -> None:
    result = audit(
        facts(
            line(1, C.SURGEON, 20_000),
            line(2, C.DIAGNOSTICS, 10_000),
            line(3, C.IMPLANT, 40_000),
            line(4, C.CONSUMABLE, 0),
            documents=present,
            policy_=policy(claims_clause_id="9.1"),
        )
    )
    assert [
        (f.flag_id, f.severity, f.amount_at_risk // 100, f.lines) for f in result.flags
    ] == expected
    assert all(f.citation_refs == ("policy:9.1",) for f in result.flags)
    assert all(f.missing_document for f in result.flags)


def test_zero_amount_lines_need_no_supporting_document() -> None:
    result = audit(
        facts(line(1, C.SURGEON, 100), line(2, C.IMPLANT, 0), documents=(D.DISCHARGE_SUMMARY,))
    )
    assert result.flags == ()
