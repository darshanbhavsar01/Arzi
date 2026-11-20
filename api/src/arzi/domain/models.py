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
    PolicyTermKind,
    ReasoningStatus,
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
LongText = Annotated[str, Field(max_length=6000)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
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


RunStatus = Literal["queued", "running", "completed", "failed"]
RunEventType = Literal[
    "stage.started", "stage.completed", "flag.created", "run.completed", "run.failed"
]


class RunEvent(_Value):
    """One streamed pipeline event; ``seq`` doubles as the SSE event id for resumption."""

    seq: Annotated[int, Field(ge=1)]
    type: RunEventType
    stage: Name | None = None
    at: dt.datetime
    data: dict[str, int | str | float | bool | None] = Field(default_factory=dict)


class LlmCall(_Value):
    """Token usage and estimated cost of one model call, for the run record and the ledger."""

    prompt_ref: Name
    model: Name
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cost_micro_inr: int = 0
    replayed: bool = False


class AuditRun(_Value):
    """One pipeline execution. Persisted as its own document; the claim keeps a summary."""

    run_id: Name
    engine_version: Name
    status: RunStatus = "queued"
    idempotency_key: Annotated[str, Field(max_length=128)] | None = None
    started_at: dt.datetime
    finished_at: dt.datetime | None = None
    events: tuple[RunEvent, ...] = ()
    calls: tuple[LlmCall, ...] = ()
    prompt_versions: tuple[str, ...] = ()
    error: Annotated[str, Field(max_length=80)] | None = None
    """A stable error slug only, never an exception message (it could quote a document)."""

    @property
    def cost_micro_inr(self) -> int:
        return sum(call.cost_micro_inr for call in self.calls)


# --------------------------------------------------------------------------- reasoning


class Prose(_Value):
    """Model- or person-written text whose rupee amounts are placeholders.

    ``template`` holds ``{{totals.at_risk}}``-style placeholders; ``text`` is the same prose with
    each placeholder filled from the rules engine. ``text`` is None when the template could not
    be rendered (a step that needs review), so the UI shows a warning instead.
    """

    template: LongText
    text: LongText | None = None


class PolicyTermNote(_Value):
    term: PolicyTermKind
    clause_id: Name | None = None
    summary: Prose
    confidence: Annotated[float, Field(ge=0, le=1)]
    needs_confirmation: bool = False


class PolicyReview(_Value):
    """The policy interpreter's reading: which clause governs each term, in plain language."""

    status: ReasoningStatus
    prompt_ref: Name | None = None
    violations: tuple[Text, ...] = ()
    terms: tuple[PolicyTermNote, ...] = ()


class FlagNarrative(_Value):
    flag_id: Name
    headline: Prose
    explanation: Prose
    fix: Prose
    citations: tuple[Name, ...] = ()


class ClaimNarratives(_Value):
    """Plain-language explanation and fix for each flag. Amounts stay engine-owned."""

    status: ReasoningStatus
    prompt_ref: Name | None = None
    violations: tuple[Text, ...] = ()
    items: tuple[FlagNarrative, ...] = ()


# --------------------------------------------------------------------------- appeals


class AppealItem(_Value):
    """One disputed deduction or rejection. Amount and insurer reason come from the engine and
    the letter; only ``argument`` is drafted."""

    flag_id: Name
    rule_id: Name
    amount: Amount
    amount_ref: Name
    insurer_reason: Text
    argument: Prose
    citations: tuple[Name, ...] = ()


class AppealContent(_Value):
    subject: Prose
    facts: Prose
    items: tuple[AppealItem, ...]
    relief: Prose
    relief_amount: Amount
    enclosures: tuple[Text, ...] = ()


class AppealSignature(_Value):
    """Who reviewed the appeal, and the SHA-256 of exactly what they signed."""

    reviewer_name: Name
    reviewer_role: Name
    signed_by: Name
    signed_at: dt.datetime
    content_sha256: Sha256


class AppealVersion(_Value):
    """One immutable version of a claim's appeal. Edits create the next version."""

    claim_id: Name
    version: Annotated[int, Field(ge=1)]
    forum: AppealForum
    status: AppealStatus = AppealStatus.DRAFT
    content: AppealContent
    drafting: ReasoningStatus
    prompt_ref: Name | None = None
    """The drafter's prompt version; None for a version a person edited."""
    violations: tuple[Text, ...] = ()
    based_on: Annotated[int, Field(ge=1)] | None = None
    idempotency_key: Annotated[str, Field(max_length=128)] | None = None
    created_by: Name
    created_at: dt.datetime
    signature: AppealSignature | None = None
    exported_at: dt.datetime | None = None


# --------------------------------------------------------------------------- family

Language = Literal["en", "hi", "gu"]
LANGUAGES: tuple[Language, ...] = ("gu", "hi", "en")


class FamilyExplanation(_Value):
    """What happened, why and what to do next, for the patient's family, in one language.
    Amounts are engine placeholders, as everywhere else."""

    lang: Language
    status: ReasoningStatus
    prompt_ref: Name | None = None
    violations: tuple[Text, ...] = ()
    headline: Prose
    what_happened: tuple[Prose, ...] = ()
    why: tuple[Prose, ...] = ()
    next_steps: tuple[Prose, ...] = ()
    reassurance: Prose


class FamilyAudio(_Value):
    """A narrated explanation, synthesised once per language."""

    lang: Language
    uri: Text
    content_type: Literal["audio/mpeg", "audio/wav"]
    seconds: Annotated[float, Field(ge=0)]
    model: Name
    adapter: Literal["gemini_tts", "replay", "fake"]
    text_sha256: Sha256


class FamilyPack(_Value):
    explanations: tuple[FamilyExplanation, ...] = ()
    audio: tuple[FamilyAudio, ...] = ()
    generated_at: dt.datetime | None = None


class ShareLink(_Value):
    """A family link. Only the SHA-256 of the token is stored; the token is shown once."""

    token_sha256: Sha256
    hospital_id: Name
    claim_id: Name
    purpose: Literal["family", "public_check"] = "family"
    created_by: Name
    created_at: dt.datetime
    expires_at: dt.datetime
    revoked_at: dt.datetime | None = None

    def active(self, now: dt.datetime) -> bool:
        return self.revoked_at is None and now < self.expires_at


class FlagReview(_Value):
    """A person's decision on one flag: accepted as a real risk, or dismissed with a reason."""

    flag_id: Name
    decision: Literal["accepted", "dismissed"]
    reason: Text = ""
    by: Name
    at: dt.datetime


class AppealSummary(_Value):
    appeal_id: Name
    forum: AppealForum
    version: Annotated[int, Field(ge=1)] = 1
    status: AppealStatus = AppealStatus.DRAFT
    content_sha256: Sha256 | None = None


class Consent(_Value):
    """DPDP consent for processing this claim's documents, recorded before any extraction."""

    given_by: Name
    purpose: Literal["claim_audit"] = "claim_audit"
    recorded_by: Name
    at: dt.datetime


class ReviewIssue(_Value):
    """Something a person must confirm before the numbers can be trusted."""

    code: Literal[
        "low_confidence_line",
        "total_mismatch",
        "unreadable_amount",
        "unmapped_deduction",
        "cap_unresolved",
        "missing_document",
        "missing_field",
        "policy_term_unconfirmed",
    ]
    message: Text
    line_id: int | None = None


class RedactionSummary(_Value):
    """What redaction replaced, by identifier kind (counts only; never the values)."""

    counts: dict[str, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


class ClaimRecord(_Value):
    """The persisted claim, scoped to one hospital (tenant). Evolve it with ``model_copy``.

    ``revision`` is the optimistic-concurrency token: a write succeeds only if the stored
    revision still equals the one the writer read.
    """

    hospital_id: Name
    claim_id: Name
    mode: ClaimMode = ClaimMode.PRE_SUBMISSION
    insurer_hint: Name | None = None
    status: ClaimStatus = ClaimStatus.DRAFT
    schema_version: int = SCHEMA_VERSION
    revision: int = 0
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None
    consent: Consent | None = None
    facts: ClaimFacts | None = None
    audit: AuditResult | None = None
    issues: tuple[ReviewIssue, ...] = ()
    redaction: RedactionSummary | None = None
    policy_review: PolicyReview | None = None
    narratives: ClaimNarratives | None = None
    document_types: dict[str, Name] = Field(default_factory=dict)
    """Document ID → type, as chosen at upload or classified by the last run."""
    flag_reviews: tuple[FlagReview, ...] = ()
    family: FamilyPack | None = None
    """Family explanations and narrated audio, generated when the desk first shares the claim."""
    runs: tuple[AuditRun, ...] = ()
    appeals: tuple[AppealSummary, ...] = ()
    audit_refs: tuple[str, ...] = ()
