from datetime import date
from decimal import Decimal

import pytest
from pydantic import TypeAdapter, ValidationError

from arzi.domain.enums import (
    ClaimMode,
    ClaimStatus,
    DeductionReason,
    InsurerLetterType,
    LineCategory,
    RejectionGround,
)
from arzi.domain.models import (
    Admission,
    BillLine,
    CategoryCap,
    ClaimRecord,
    InsurerDeduction,
    InsurerLetter,
    PctOfSumInsuredCap,
    PerDayAmountCap,
    RoomRentCap,
)
from arzi.domain.money import rupees
from tests.builders import facts, line, policy

C = LineCategory


def test_room_rent_cap_is_a_discriminated_union() -> None:
    adapter: TypeAdapter[RoomRentCap] = TypeAdapter(RoomRentCap)

    assert isinstance(
        adapter.validate_python({"type": "per_day_amount", "amount": 1}), PerDayAmountCap
    )
    assert isinstance(
        adapter.validate_python({"type": "pct_of_si", "pct": "1"}), PctOfSumInsuredCap
    )
    assert isinstance(
        adapter.validate_python({"type": "category", "category": "Twin"}), CategoryCap
    )
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "per_day_amount", "pct": "1"})


def test_money_fields_reject_negatives() -> None:
    with pytest.raises(ValidationError):
        BillLine.model_validate(
            {"line_id": 1, "description": "x", "category": "room", "amount": -1}
        )


def test_values_are_frozen() -> None:
    bill_line = line(1, C.ROOM, 100)
    with pytest.raises(ValidationError):
        bill_line.amount = rupees(1)  # type: ignore[misc]  # asserting immutability


def test_facts_round_trip_through_json() -> None:
    original = facts(line(1, C.ROOM, 8_000, qty=4), line(2, C.PHARMACY, 100))
    assert type(original).model_validate_json(original.model_dump_json()) == original


def test_duplicate_line_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        facts(line(1, C.ROOM, 1), line(1, C.PHARMACY, 1))


@pytest.mark.parametrize(
    ("mode", "letter_type"),
    [
        (ClaimMode.POST_DEDUCTION, None),
        (ClaimMode.POST_DEDUCTION, InsurerLetterType.REJECTION),
        (ClaimMode.POST_REJECTION, InsurerLetterType.DEDUCTION),
    ],
)
def test_post_modes_need_the_matching_letter(
    mode: ClaimMode, letter_type: InsurerLetterType | None
) -> None:
    letter = (
        InsurerLetter(
            type=letter_type, amount_claimed=rupees(1), rejection_ground=RejectionGround.OTHER
        )
        if letter_type
        else None
    )
    with pytest.raises(ValidationError, match="needs an insurer letter"):
        facts(line(1, C.ROOM, 1), mode=mode, letter=letter)


def test_pre_submission_accepts_a_query_letter() -> None:
    letter = InsurerLetter(type=InsurerLetterType.QUERY, amount_claimed=rupees(1))
    assert facts(line(1, C.ROOM, 1), letter=letter).insurer_letter == letter


def test_rejection_letter_needs_a_ground() -> None:
    with pytest.raises(ValidationError, match="rejection_ground"):
        InsurerLetter(type=InsurerLetterType.REJECTION, amount_claimed=rupees(1))


def test_deductions_must_reference_known_lines() -> None:
    letter = InsurerLetter(
        type=InsurerLetterType.DEDUCTION,
        amount_claimed=rupees(1),
        deductions=(
            InsurerDeduction(line_id=None, amount=rupees(1), reason=DeductionReason.COPAY),
            InsurerDeduction(line_id=9, amount=rupees(1), reason=DeductionReason.OTHER),
        ),
    )
    with pytest.raises(ValidationError, match="unknown bill lines"):
        facts(line(1, C.ROOM, 1), mode=ClaimMode.POST_DEDUCTION, letter=letter)


def test_discharge_cannot_precede_admission() -> None:
    with pytest.raises(ValidationError, match="before"):
        Admission(date_in=date(2026, 11, 5), date_out=date(2026, 11, 1))
    assert Admission(date_in=date(2026, 11, 1), date_out=date(2026, 11, 1)).date_out


def test_patient_must_be_pseudonymous() -> None:
    with pytest.raises(ValidationError):
        facts(line(1, C.ROOM, 1)).patient.model_validate({"redacted_id": "Ramesh Patel"})


def test_quantity_and_percent_bounds() -> None:
    with pytest.raises(ValidationError):
        line(1, C.ROOM, 1, qty=0)
    with pytest.raises(ValidationError):
        policy(copay={"pct": Decimal(101)})


def test_claim_record_defaults_to_draft() -> None:
    record = ClaimRecord(hospital_id="H-001", claim_id="ARZ-1")
    assert record.status is ClaimStatus.DRAFT
    assert record.schema_version == 1
    assert record.model_copy(update={"status": ClaimStatus.AUDITED}).status is ClaimStatus.AUDITED
