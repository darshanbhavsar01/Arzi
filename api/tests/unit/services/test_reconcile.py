import datetime as dt
from decimal import Decimal
from typing import Any

import pytest

from arzi.adapters.demo_seed import DEMO_HOSPITAL
from arzi.domain.enums import ClaimMode, CopayBase, DeductionReason, RejectionGround
from arzi.domain.models import CategoryCap, PctOfSumInsuredCap, PerDayAmountCap
from arzi.domain.money import rupees
from arzi.services.extraction_schemas import (
    BillExtraction,
    BillLineText,
    ClauseText,
    CopayText,
    DeductionText,
    DischargeExtraction,
    DocType,
    InsurerLetterExtraction,
    LetterKind,
    PolicyExtraction,
    ReasonCode,
    RoomRentCapKind,
    RoomRentCapText,
    SubLimitText,
)
from arzi.services.reconcile import (
    FactsIncompleteError,
    ReconcileInput,
    match_line,
    months_between,
    parse_date,
    reconcile,
)


def _line(serial: int, description: str, amount: str, **extra: Any) -> BillLineText:  # noqa: ANN401 - test builder
    fields: dict[str, Any] = {
        "serial": serial,
        "description": description,
        "category": "surgeon",
        "qty": "1",
        "amount": amount,
        "page": 1,
        "confidence": 0.95,
    }
    fields.update(extra)
    return BillLineText(**fields)


BILL = BillExtraction(
    admission_date="2026-10-12",
    discharge_date="2026-10-17",
    lines=[
        _line(1, "Surgeon fees", "60,000.00"),
        _line(2, "Laundry charges", "1,200.00", category="non_payable"),
    ],
    printed_total="61,200.00",
)
POLICY = PolicyExtraction(
    insurer="Suraksha Health Insurance Co. (fictional)",
    sum_insured="Rs. 5,00,000.00",
    first_inception_date="2024-04-12",
    clauses=[
        ClauseText(id="4.3", title="Proportionate deduction", text="...", page=1),
        ClauseText(id="9.2", title="Claim documents", text="...", page=3),
        ClauseText(id="4.4", title="ICU charges", text="...", page=1),
    ],
)


def _input(**overrides: Any) -> ReconcileInput:  # noqa: ANN401 - test builder
    fields: dict[str, Any] = {
        "claim_id": "ARZ-1",
        "mode": ClaimMode.PRE_SUBMISSION,
        "hospital": DEMO_HOSPITAL,
        "patient_pseudonym": "P-ABCD",
        "document_types": [DocType.ITEMISED_BILL, DocType.POLICY_SCHEDULE],
        "policies": [POLICY],
        "bills": [BILL],
    }
    fields.update(overrides)
    return ReconcileInput(**fields)


def _codes(outcome: Any) -> list[str]:  # noqa: ANN401 - test builder
    return [issue.code for issue in outcome.issues]


def test_clean_documents_reconcile_without_issues() -> None:
    outcome = reconcile(_input())
    facts = outcome.facts
    assert outcome.issues == []
    assert [line.amount for line in facts.bill_lines] == [rupees(60_000), rupees(1_200)]
    assert facts.policy.continuous_cover_months == 30
    assert facts.policy.proportionate_clause_id == "4.3"
    assert facts.policy.claims_clause_id == "9.2"
    assert facts.patient.redacted_id == "P-ABCD"
    assert [str(k) for k in facts.documents_present] == ["itemised_bill", "policy"]


def test_mismatched_total_and_low_confidence_need_confirmation() -> None:
    bill = BILL.model_copy(
        update={
            "lines": [_line(1, "Surgeon fees", "60,000.00", confidence=0.5)],
            "printed_total": "61,000.00",
        }
    )
    outcome = reconcile(_input(bills=[bill]))
    assert _codes(outcome) == ["low_confidence_line", "total_mismatch"]
    assert outcome.issues[0].line_id == 1


def test_unreadable_amount_and_quantity() -> None:
    bill = BILL.model_copy(
        update={
            "lines": [
                _line(1, "Surgeon fees", "illegible"),
                _line(2, "Room", "8,000.00", qty="four"),
            ],
            "printed_total": None,
        }
    )
    outcome = reconcile(_input(bills=[bill]))
    assert _codes(outcome) == ["unreadable_amount", "unreadable_amount"]
    assert [line.qty for line in outcome.facts.bill_lines] == [Decimal(1)]


def test_without_a_readable_bill_the_run_stops() -> None:
    with pytest.raises(FactsIncompleteError):
        reconcile(_input(bills=[]))
    with pytest.raises(FactsIncompleteError):
        reconcile(_input(bills=[BILL.model_copy(update={"lines": [_line(1, "x", "?")]})]))


@pytest.mark.parametrize(
    ("cap", "expected"),
    [
        (
            RoomRentCapText(kind=RoomRentCapKind.PER_DAY_AMOUNT, amount="Rs. 5,000", clause="4.2"),
            PerDayAmountCap,
        ),
        (
            RoomRentCapText(kind=RoomRentCapKind.PCT_OF_SUM_INSURED, percent="1%"),
            PctOfSumInsuredCap,
        ),
        (RoomRentCapText(kind=RoomRentCapKind.ROOM_CATEGORY, category="Twin sharing"), CategoryCap),
        (RoomRentCapText(kind=RoomRentCapKind.NO_LIMIT), type(None)),
    ],
)
def test_room_rent_cap_kinds(cap: RoomRentCapText, expected: type) -> None:
    policy = POLICY.model_copy(update={"room_rent_cap": cap})
    assert isinstance(reconcile(_input(policies=[policy])).facts.policy.room_rent_cap, expected)


def test_unreadable_cap_copay_and_sub_limit_are_flagged() -> None:
    policy = POLICY.model_copy(
        update={
            "room_rent_cap": RoomRentCapText(
                kind=RoomRentCapKind.PER_DAY_AMOUNT, amount="as per schedule"
            ),
            "copay": CopayText(percent="as applicable"),
            "sub_limits": [SubLimitText(item="Cataract", limit="per policy")],
        }
    )
    outcome = reconcile(_input(policies=[policy]))
    assert _codes(outcome) == ["cap_unresolved", "missing_field", "missing_field"]


def test_copay_icu_cap_and_merged_policies() -> None:
    schedule = PolicyExtraction(
        sum_insured="Rs. 3,00,000",
        first_inception_date="2024-04-12",
        copay=CopayText(percent="20", on_claimed_amount=True, clause="7.4"),
        icu_cap_per_day="Rs. 10,000",
        sub_limits=[SubLimitText(item="Cataract", limit="Rs. 40,000", clause="6.1")],
    )
    outcome = reconcile(_input(policies=[schedule, POLICY]))
    policy = outcome.facts.policy
    assert policy.sum_insured == rupees(300_000)
    assert policy.copay is not None
    assert policy.copay.base is CopayBase.CLAIMED
    assert policy.copay.pct == Decimal(20)
    assert policy.icu_cap is not None
    assert policy.icu_cap.clause_id == "4.4"
    assert policy.sub_limits[0].limit == rupees(40_000)
    assert len(policy.clauses) == 3
    no_limit = schedule.model_copy(
        update={"icu_cap_per_day": "No limit (actual charges)", "copay": CopayText()}
    )
    assert reconcile(_input(policies=[no_limit])).facts.policy.icu_cap is None


def test_missing_policy_and_dates_are_flagged() -> None:
    outcome = reconcile(
        _input(policies=[], bills=[BILL.model_copy(update={"admission_date": None})])
    )
    assert _codes(outcome) == ["missing_document", "missing_field", "missing_field"]
    assert outcome.facts.policy.continuous_cover_months == 0


def test_discharge_summary_wins_for_admission_details() -> None:
    discharge = DischargeExtraction(
        admission_date="12-Oct-2026",
        discharge_date="2026-10-01",  # before admission: discarded, not trusted
        diagnosis="Fracture of neck of right femur",
        procedure="Right hip hemiarthroplasty",
        patient_age=67,
    )
    facts = reconcile(_input(discharges=[discharge])).facts
    assert facts.admission.date_in == dt.date(2026, 10, 12)
    assert facts.admission.date_out is None
    assert facts.admission.procedure == "Right hip hemiarthroplasty"
    assert facts.patient.age == 67


def test_deduction_letter_maps_rows_to_bill_lines() -> None:
    letter = InsurerLetterExtraction(
        kind=LetterKind.DEDUCTION,
        letter_date="2026-11-02",
        amount_claimed="Rs. 61,200.00",
        amount_approved="Rs. 50,000.00",
        deductions=[
            DeductionText(
                bill_item="Surgeon Fees",
                deducted="10,000.00",
                reason="Proportionate",
                reason_code=ReasonCode.PROPORTIONATE,
                clause="4.3",
            ),
            DeductionText(
                bill_item="Laundry",
                deducted="1,200.00",
                reason="Non-medical",
                reason_code=ReasonCode.NON_PAYABLE,
            ),
            DeductionText(
                bill_item="Claim level",
                deducted="100.00",
                reason="Co-pay",
                reason_code=ReasonCode.COPAY,
            ),
            DeductionText(
                bill_item="Television", deducted="50.00", reason="x", reason_code=ReasonCode.OTHER
            ),
            DeductionText(
                bill_item="Surgeon fees", deducted="n/a", reason="x", reason_code=ReasonCode.OTHER
            ),
        ],
    )
    outcome = reconcile(_input(mode=ClaimMode.POST_DEDUCTION, letters=[letter]))
    deductions = outcome.facts.insurer_letter.deductions if outcome.facts.insurer_letter else ()
    assert [(d.line_id, d.reason) for d in deductions] == [
        (1, DeductionReason.PROPORTIONATE),
        (2, DeductionReason.NON_PAYABLE),
        (None, DeductionReason.COPAY),
        (None, DeductionReason.OTHER),
    ]
    assert _codes(outcome) == ["unmapped_deduction", "unreadable_amount"]


def test_rejection_letter_without_a_code_is_other_and_letters_are_required() -> None:
    letter = InsurerLetterExtraction(kind=LetterKind.REJECTION, amount_claimed=None)
    outcome = reconcile(_input(mode=ClaimMode.POST_REJECTION, letters=[letter]))
    assert outcome.facts.insurer_letter is not None
    assert outcome.facts.insurer_letter.rejection_ground is RejectionGround.OTHER
    assert outcome.facts.insurer_letter.amount_claimed == rupees(61_200)
    assert "missing_field" in _codes(outcome)
    with pytest.raises(FactsIncompleteError):
        reconcile(_input(mode=ClaimMode.POST_REJECTION))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-10-12", dt.date(2026, 10, 12)),
        ("12-Oct-2026", dt.date(2026, 10, 12)),
        ("12/10/2026", dt.date(2026, 10, 12)),
        ("12 October 2026", dt.date(2026, 10, 12)),
        ("someday", None),
        (None, None),
    ],
)
def test_parse_date(text: str | None, expected: dt.date | None) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    ("start", "end", "months"),
    [
        (dt.date(2024, 4, 12), dt.date(2026, 10, 12), 30),
        (dt.date(2023, 6, 20), dt.date(2026, 10, 20), 40),
        (dt.date(2023, 6, 20), dt.date(2026, 10, 19), 39),
        (dt.date(2026, 10, 20), dt.date(2026, 1, 1), 0),
    ],
)
def test_months_between_counts_completed_months(start: dt.date, end: dt.date, months: int) -> None:
    assert months_between(start, end) == months


def test_match_line_fuzzy() -> None:
    facts = reconcile(_input()).facts
    assert match_line("LAUNDRY CHARGES", facts.bill_lines) == 2
    assert match_line("Laundary charges", facts.bill_lines) == 2
    assert match_line("Laundry", facts.bill_lines) == 2  # abbreviated in the letter
    assert match_line("Pharmacy", facts.bill_lines) is None


def test_match_line_refuses_ambiguous_rows() -> None:
    bill = BILL.model_copy(
        update={
            "lines": [_line(1, "Surgeon charges", "1"), _line(2, "Nursing charges", "1")],
            "printed_total": None,
        }
    )
    facts = reconcile(_input(bills=[bill])).facts
    assert match_line("Charges", facts.bill_lines) is None
