"""Claim facts (engine input), audit results (engine output) and the persisted claim record.

``ClaimFacts`` is deliberately separate from ``ClaimRecord``: the engine sees only confirmed,
redacted facts and returns values; persistence, runs, appeals and tenancy live around it.
All money is integer paise (``Paise``); value objects are frozen.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arzi.domain.enums import (
    AppealForum,
    AppealStatus,
    ClaimMode,
    ClaimStatus,
    CopayBase,
    DeductionReason,
    DocumentKind,
    FixCode,
    FlagKind,
    InsurerLetterType,
    IrdaiList,
    LineCategory,
    RejectionGround,
    RoomRentCapType,
    Severity,
)
from arzi.domain.money import ZERO, Paise

Amount = Annotated[Paise, Field(ge=0)]
Percent = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=9, decimal_places=3)]
Months = Annotated[int, Field(ge=0, le=1200)]
Text = Annotated[str, Field(max_length=2000)]
Name = Annotated[str, Field(min_length=1, max_length=200)]

SCHEMA_VERSION = 1

DEFAULT_ASSOCIATED_CATEGORIES: tuple[LineCategory, ...] = (
    LineCategory.SURGEON,
    LineCategory.ANAESTHETIST,
    LineCategory.OT,
    LineCategory.NURSING,
    LineCategory.CONSULTATION,
)


class _Value(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- facts


class RoomCategory(_Value):
    name: Name
    rate_per_day: Amount


class Hospital(_Value):
    name: Name
    city: Text = ""
    room_categories: tuple[RoomCategory, ...] = ()


class Patient(_Value):
    """Only the pseudonym reaches the engine; raw identifiers stay in a restricted field."""

    redacted_id: Annotated[str, Field(pattern=r"^P-[0-9A-Z]{4,12}$")]
    age: Annotated[int, Field(ge=0, le=130)] | None = None


class PerDayAmountCap(_Value):
    type: Literal[RoomRentCapType.PER_DAY_AMOUNT]
    amount: Amount
    clause_id: Name | None = None


class PctOfSumInsuredCap(_Value):
    type: Literal[RoomRentCapType.PCT_OF_SI]
    pct: Percent
    clause_id: Name | None = None


class CategoryCap(_Value):
    """Cap expressed as a room category ("single private AC"); the hospital tariff prices it."""

    type: Literal[RoomRentCapType.CATEGORY]
    category: Name
    clause_id: Name | None = None


RoomRentCap = Annotated[
    PerDayAmountCap | PctOfSumInsuredCap | CategoryCap, Field(discriminator="type")
]


class IcuCap(_Value):
    amount_per_day: Amount
    clause_id: Name | None = None


class Copay(_Value):
    pct: Percent
    base: CopayBase = CopayBase.ADMISSIBLE
    clause_id: Name | None = None


class WaitingCondition(_Value):
    condition: Name
    waiting_months: Months
    clause_id: Name | None = None


class SubLimit(_Value):
    """A cap on what is payable for a named procedure or condition.

    ``categories`` narrows the cap to some bill-line categories (e.g. the lens in cataract);
    empty means the whole claim.
    """

    item: Name
    limit: Amount
    categories: tuple[LineCategory, ...] = ()
    clause_id: Name | None = None


class PolicyClause(_Value):
    id: Name
    title: Text
    text: Annotated[str, Field(max_length=20_000)] = ""
    page: Annotated[int, Field(ge=1)] | None = None


class Policy(_Value):
    insurer: Name
    product: Text = ""
    sum_insured: Amount
    continuous_cover_months: Months
    room_rent_cap: RoomRentCap | None = None
    proportionate_clause_id: Name | None = None
    icu_cap: IcuCap | None = None
    copay: Copay | None = None
    associated_expense_categories: tuple[LineCategory, ...] = DEFAULT_ASSOCIATED_CATEGORIES
    ped_declared: tuple[WaitingCondition, ...] = ()
    specific_waiting: tuple[WaitingCondition, ...] = ()
    sub_limits: tuple[SubLimit, ...] = ()
    non_payable_addon: bool = False
    claims_clause_id: Name | None = None
    clauses: tuple[PolicyClause, ...] = ()


class Admission(_Value):
    date_in: dt.date | None = None
    date_out: dt.date | None = None
    diagnosis: Text = ""
    procedure: Text = ""
    icd10: Annotated[str, Field(max_length=16)] | None = None
    room_category_used: Name | None = None

    @model_validator(mode="after")
    def _discharge_after_admission(self) -> Self:
        if self.date_in and self.date_out and self.date_out < self.date_in:
            raise ValueError("date_out is before date_in")
        return self


class BillLine(_Value):
    line_id: Annotated[int, Field(ge=1)]
    description: Name
    category: LineCategory
    amount: Amount
    qty: Quantity = Decimal(1)
    source_page: Annotated[int, Field(ge=1)] | None = None
    confidence: Annotated[float, Field(ge=0, le=1)] = 1.0
    irdai_list: IrdaiList | None = None
    confirmed_by_human: bool = False


class InsurerDeduction(_Value):
    """One cut from the insurer's settlement letter; ``line_id`` is None for claim-level cuts."""

    line_id: Annotated[int, Field(ge=1)] | None = None
    amount: Amount
    reason: DeductionReason
    reason_text: Text = ""
    clause_cited: Name | None = None


class InsurerLetter(_Value):
    type: InsurerLetterType
    date: dt.date | None = None
    amount_claimed: Amount
    amount_approved: Amount = ZERO
    deductions: tuple[InsurerDeduction, ...] = ()
    rejection_ground: RejectionGround | None = None
    fraud_alleged: bool = False

    @model_validator(mode="after")
    def _rejection_has_ground(self) -> Self:
        if self.type is InsurerLetterType.REJECTION and self.rejection_ground is None:
            raise ValueError("a rejection letter needs a rejection_ground")
        return self


_LETTER_FOR_MODE = {
    ClaimMode.POST_DEDUCTION: InsurerLetterType.DEDUCTION,
    ClaimMode.POST_REJECTION: InsurerLetterType.REJECTION,
}


class ClaimFacts(_Value):
    """Everything the rules engine needs, already extracted, confirmed and redacted."""

    claim_id: Name
    mode: ClaimMode
    hospital: Hospital
    patient: Patient
    policy: Policy
    admission: Admission = Admission()
    bill_lines: Annotated[tuple[BillLine, ...], Field(min_length=1)]
    insurer_letter: InsurerLetter | None = None
    documents_present: tuple[DocumentKind, ...] = ()

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        line_ids = [line.line_id for line in self.bill_lines]
        if len(set(line_ids)) != len(line_ids):
            raise ValueError("bill line_ids must be unique")
        expected_letter = _LETTER_FOR_MODE.get(self.mode)
        letter_type = self.insurer_letter.type if self.insurer_letter else None
        if expected_letter is not None and letter_type is not expected_letter:
            raise ValueError(f"{self.mode} needs an insurer letter of type {expected_letter}")
        cited = (
            {d.line_id for d in self.insurer_letter.deductions} if self.insurer_letter else set()
        )
        if not cited <= {*line_ids, None}:
            raise ValueError("insurer deductions reference unknown bill lines")
        return self


# --------------------------------------------------------------------------- engine output


class Flag(_Value):
    """One finding. Narrative text is added later, by the explainer, in a separate model."""

    flag_id: Annotated[str, Field(pattern=r"^[A-Z_]+(-[a-z0-9_]+)?$")]
    rule_id: Name
    kind: FlagKind
    severity: Severity
    amount_at_risk: Amount
    recoverable: Amount = ZERO
    lines: tuple[int, ...] = ()
    citation_refs: tuple[str, ...] = ()
    fix_code: FixCode | None = None
    fix_savings: Amount = ZERO
    appealable: bool = False
    trace_ref: Name
    missing_document: DocumentKind | None = None


class Totals(_Value):
    """``billed = predicted_payable + at_risk``; recoverable is what an appeal can win back."""

    billed: Amount
    predicted_payable: Amount
    at_risk: Amount
    recoverable_on_appeal: Amount


class TraceStep(_Value):
    """One human-readable computation, e.g. ``₹93,000 × 5,000 / 8,000 = ₹58,125``."""

    step_id: Name
    rule_id: Name
    formula: Text
    inputs: dict[str, int | str] = Field(default_factory=dict)
    result: Paise | None = None


class LineDeduction(_Value):
    rule_id: Name
    amount: Amount


class LineOutcome(_Value):
    line_id: int
    billed: Amount
    admissible: Amount
    deductions: tuple[LineDeduction, ...] = ()


class AuditResult(_Value):
    engine_version: Name
    mode: ClaimMode
    flags: tuple[Flag, ...]
    totals: Totals
    trace: tuple[TraceStep, ...]
    lines: tuple[LineOutcome, ...]
    fix_savings: Amount = ZERO


# --------------------------------------------------------------------------- persistence


class AuditRun(_Value):
    run_id: Name
    engine_version: Name
    started_at: dt.datetime
    finished_at: dt.datetime | None = None


class AppealSummary(_Value):
    appeal_id: Name
    forum: AppealForum
    version: Annotated[int, Field(ge=1)] = 1
    status: AppealStatus = AppealStatus.DRAFT
    content_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None


class ClaimRecord(_Value):
    """The persisted claim, scoped to one hospital (tenant). Evolve it with ``model_copy``."""

    hospital_id: Name
    claim_id: Name
    status: ClaimStatus = ClaimStatus.DRAFT
    schema_version: int = SCHEMA_VERSION
    facts: ClaimFacts | None = None
    audit: AuditResult | None = None
    runs: tuple[AuditRun, ...] = ()
    appeals: tuple[AppealSummary, ...] = ()
    audit_refs: tuple[str, ...] = ()
