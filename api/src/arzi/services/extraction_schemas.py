"""Response schemas for Gemini structured extraction.

These describe what the model *transcribes*, not what Arzi concludes: amounts are the printed
strings ("Rs. 8,000.00"), clause numbers are verbatim, dates are as printed or ISO. Code in
``reconcile`` parses and checks them. Enums are used only where the model classifies (a
document's type, a bill line's service head, an insurer's stated reason).

Kept to the subset of JSON Schema that Vertex AI structured output accepts: nested objects,
lists, enums and optional scalars, no unions of objects.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from arzi.domain.enums import LineCategory


class _Schema(BaseModel):
    model_config = ConfigDict(frozen=True)


class DocType(StrEnum):
    POLICY_SCHEDULE = "policy_schedule"
    POLICY_WORDING = "policy_wording"
    ITEMISED_BILL = "itemised_bill"
    DISCHARGE_SUMMARY = "discharge_summary"
    INVESTIGATION_REPORT = "investigation_report"
    IMPLANT_INVOICE = "implant_invoice"
    INSURER_LETTER = "insurer_letter"
    OTHER = "other"


class Classification(_Schema):
    document_type: DocType
    confidence: float = Field(ge=0, le=1)


# --------------------------------------------------------------------------- shared identity


class PersonIdentifiers(_Schema):
    """Identifiers printed on the document. Captured only so redaction can remove them."""

    patient_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    aadhaar: str | None = None
    pan: str | None = None
    uhid: str | None = None
    ip_number: str | None = None
    policy_number: str | None = None
    member_id: str | None = None
    claim_number: str | None = None


# --------------------------------------------------------------------------- policy


class RoomRentCapKind(StrEnum):
    PER_DAY_AMOUNT = "per_day_amount"
    PCT_OF_SUM_INSURED = "pct_of_sum_insured"
    ROOM_CATEGORY = "room_category"
    NO_LIMIT = "no_limit"


class RoomRentCapText(_Schema):
    kind: RoomRentCapKind
    amount: str | None = Field(None, description="Printed amount per day, e.g. 'Rs. 5,000'")
    percent: str | None = Field(None, description="Printed percentage, e.g. '1'")
    category: str | None = Field(None, description="Eligible room category name")
    clause: str | None = None


class CopayText(_Schema):
    percent: str | None = Field(None, description="Printed co-payment percentage; null if nil")
    on_claimed_amount: bool = Field(
        False, description="True only if the policy applies co-pay to the claimed amount"
    )
    clause: str | None = None


class WaitingText(_Schema):
    condition: str
    months: int = Field(ge=0)
    clause: str | None = None


class SubLimitText(_Schema):
    item: str
    limit: str = Field(description="Printed amount")
    clause: str | None = None


class ClauseText(_Schema):
    id: str = Field(description="Clause number exactly as printed, e.g. '4.3'")
    title: str
    text: str
    page: int = Field(ge=1)


class PolicyExtraction(_Schema):
    """Policy schedule and/or wording; fields absent from this document are null or empty."""

    identifiers: PersonIdentifiers = PersonIdentifiers()
    insurer: str | None = None
    product: str | None = None
    sum_insured: str | None = None
    first_inception_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    room_rent_cap: RoomRentCapText | None = None
    icu_cap_per_day: str | None = Field(None, description="Printed amount, null if no limit")
    copay: CopayText | None = None
    sub_limits: list[SubLimitText] = []
    specific_waiting: list[WaitingText] = []
    ped_declared: list[WaitingText] = []
    non_medical_cover_opted: bool | None = None
    clauses: list[ClauseText] = []


# --------------------------------------------------------------------------- bill


class BillLineText(_Schema):
    serial: int = Field(ge=1)
    description: str
    category: LineCategory = Field(description="Best-fit service head for this line")
    qty: str = Field(description="Printed quantity, e.g. '4'")
    rate: str | None = None
    amount: str = Field(description="Printed line amount")
    page: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1, description="How sure the transcription is correct")


class BillExtraction(_Schema):
    identifiers: PersonIdentifiers = PersonIdentifiers()
    hospital_name: str | None = None
    patient_age: int | None = None
    admission_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    discharge_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    room_category: str | None = None
    lines: list[BillLineText] = []
    printed_total: str | None = Field(None, description="Grand total as printed")


# --------------------------------------------------------------------------- discharge


class DischargeExtraction(_Schema):
    identifiers: PersonIdentifiers = PersonIdentifiers()
    patient_age: int | None = None
    admission_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    discharge_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    diagnosis: str | None = None
    icd10: str | None = None
    procedure: str | None = None
    room_category: str | None = None


# --------------------------------------------------------------------------- insurer letter


class LetterKind(StrEnum):
    DEDUCTION = "deduction"
    REJECTION = "rejection"
    QUERY = "query"


class ReasonCode(StrEnum):
    PROPORTIONATE = "proportionate"
    ROOM_RENT_EXCESS = "room_rent_excess"
    ICU_CAP = "icu_cap"
    NON_PAYABLE = "non_payable"
    SUB_LIMIT = "sub_limit"
    COPAY = "copay"
    OTHER = "other"


class RejectionCode(StrEnum):
    PED_WAITING = "ped_waiting"
    SPECIFIC_WAITING = "specific_waiting"
    NON_DISCLOSURE = "non_disclosure"
    OTHER = "other"


class DeductionText(_Schema):
    bill_item: str = Field(description="Bill item as written in the letter, or 'Claim level'")
    deducted: str = Field(description="Printed deducted amount")
    reason: str
    reason_code: ReasonCode
    clause: str | None = None


class InsurerLetterExtraction(_Schema):
    identifiers: PersonIdentifiers = PersonIdentifiers()
    kind: LetterKind
    letter_date: str | None = Field(None, description="ISO date YYYY-MM-DD")
    amount_claimed: str | None = None
    amount_approved: str | None = None
    deductions: list[DeductionText] = []
    rejection_code: RejectionCode | None = None
    rejection_reason: str | None = None
    fraud_alleged: bool = False


EXTRACTION_SCHEMAS: dict[DocType, type[_Schema]] = {
    DocType.POLICY_SCHEDULE: PolicyExtraction,
    DocType.POLICY_WORDING: PolicyExtraction,
    DocType.ITEMISED_BILL: BillExtraction,
    DocType.DISCHARGE_SUMMARY: DischargeExtraction,
    DocType.INSURER_LETTER: InsurerLetterExtraction,
}
"""Types that need field extraction. Reports and implant invoices only need to be present."""
