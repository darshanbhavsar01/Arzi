"""Closed vocabularies shared by the engine, the API and the UI.

String enums so values read the same in Firestore, JSON, logs and the generated TypeScript
client.
"""

from enum import StrEnum


class ClaimMode(StrEnum):
    """Where the claim is in its life, which decides which rules can fire."""

    PRE_SUBMISSION = "pre_submission"
    POST_DEDUCTION = "post_deduction"
    POST_REJECTION = "post_rejection"


class LineCategory(StrEnum):
    ROOM = "room"
    ICU = "icu"
    SURGEON = "surgeon"
    ANAESTHETIST = "anaesthetist"
    OT = "ot"
    NURSING = "nursing"
    CONSULTATION = "consultation"
    PHARMACY = "pharmacy"
    CONSUMABLE = "consumable"
    IMPLANT = "implant"
    DIAGNOSTICS = "diagnostics"
    NON_PAYABLE = "non_payable"
    OTHER = "other"


class IrdaiList(StrEnum):
    """IRDAI Annexure I lists: I is not payable; II-IV are subsumed into room, procedure or
    treatment cost and must not be deducted separately."""

    I = "I"  # noqa: E741 - the regulator's own list numeral
    II = "II"
    III = "III"
    IV = "IV"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FlagKind(StrEnum):
    """How a flag's amount relates to the totals.

    ``deduction``: the engine expects the insurer to cut this amount; summed into ``at_risk``.
    ``advisory``: a risk with no computed cut; the amount is the exposure, not a deduction.
    ``dispute``: the insurer cut or rejected something it should not have; ``recoverable`` is
    summed into ``recoverable_on_appeal``.
    """

    DEDUCTION = "deduction"
    ADVISORY = "advisory"
    DISPUTE = "dispute"


class FixCode(StrEnum):
    ROOM_DOWNGRADE_OR_CONSENT = "room_downgrade_or_consent"
    ICU_TARIFF_REVIEW = "icu_tariff_review"
    COLLECT_FROM_PATIENT = "collect_from_patient"
    BILL_WITHIN_PACKAGE = "bill_within_package"
    INFORM_PATIENT = "inform_patient"
    CHECK_WAITING_PERIOD = "check_waiting_period"
    ATTACH_DOCUMENT = "attach_document"
    FILE_APPEAL = "file_appeal"


class CitationStatus(StrEnum):
    """``verify`` is rendered as an amber "Verify before filing" badge."""

    VERIFIED = "verified"
    VERIFY = "verify"


class AppealForum(StrEnum):
    INSURER_GRO = "insurer_gro"
    BIMA_BHAROSA = "bima_bharosa"
    OMBUDSMAN = "ombudsman"


class ClaimStatus(StrEnum):
    DRAFT = "draft"
    DOCUMENTS_UPLOADED = "documents_uploaded"
    PROCESSING = "processing"
    AUDITED = "audited"
    APPEAL_DRAFTED = "appeal_drafted"
    IN_REVIEW = "in_review"
    SIGNED = "signed"
    EXPORTED = "exported"
    FAILED = "failed"


class AppealStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    SIGNED = "signed"
    EXPORTED = "exported"


class RoomRentCapType(StrEnum):
    PER_DAY_AMOUNT = "per_day_amount"
    PCT_OF_SI = "pct_of_si"
    CATEGORY = "category"


class CopayBase(StrEnum):
    """What the co-pay percentage applies to; policies differ, so it is read from the clause."""

    ADMISSIBLE = "admissible"
    CLAIMED = "claimed"


class InsurerLetterType(StrEnum):
    DEDUCTION = "deduction"
    REJECTION = "rejection"
    QUERY = "query"


class DeductionReason(StrEnum):
    """The insurer's stated reason for a cut, normalised from the letter's wording."""

    PROPORTIONATE = "proportionate"
    ROOM_RENT_EXCESS = "room_rent_excess"
    ICU_CAP = "icu_cap"
    NON_PAYABLE = "non_payable"
    SUB_LIMIT = "sub_limit"
    COPAY = "copay"
    OTHER = "other"


class RejectionGround(StrEnum):
    PED_WAITING = "ped_waiting"
    SPECIFIC_WAITING = "specific_waiting"
    NON_DISCLOSURE = "non_disclosure"
    OTHER = "other"


class DocumentKind(StrEnum):
    POLICY = "policy"
    ITEMISED_BILL = "itemised_bill"
    DISCHARGE_SUMMARY = "discharge_summary"
    INVESTIGATION_REPORTS = "investigation_reports"
    IMPLANT_INVOICE = "implant_invoice"
    INSURER_LETTER = "insurer_letter"
