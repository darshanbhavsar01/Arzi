"""Small builders for ClaimFacts so each test states only what it is about."""

from decimal import Decimal
from typing import Any

from arzi.domain.enums import ClaimMode, DocumentKind, LineCategory
from arzi.domain.models import (
    Admission,
    BillLine,
    ClaimFacts,
    Hospital,
    InsurerLetter,
    Patient,
    Policy,
)
from arzi.domain.money import rupees

C = LineCategory

ALL_DOCUMENTS = tuple(DocumentKind)

_DESCRIPTIONS = {
    C.ROOM: "Ward room charges",
    C.ICU: "ICU charges",
    C.SURGEON: "Surgeon fees",
    C.ANAESTHETIST: "Anaesthetist fees",
    C.OT: "Operation theatre charges",
    C.NURSING: "Nursing charges",
    C.CONSULTATION: "Consultation charges",
    C.PHARMACY: "Pharmacy",
    C.CONSUMABLE: "Surgical consumables",
    C.IMPLANT: "Orthopaedic implant",
    C.DIAGNOSTICS: "Laboratory and imaging",
    C.NON_PAYABLE: "Miscellaneous",
    C.OTHER: "Physiotherapy",
}


def line(
    line_id: int,
    category: LineCategory,
    amount_rupees: int,
    qty: int | str = 1,
    description: str | None = None,
    **extra: Any,  # noqa: ANN401 - forwarded BillLine fields
) -> BillLine:
    return BillLine(
        line_id=line_id,
        description=description or _DESCRIPTIONS[category],
        category=category,
        amount=rupees(amount_rupees),
        qty=Decimal(qty),
        **extra,
    )


def policy(**overrides: Any) -> Policy:  # noqa: ANN401 - forwarded Policy fields
    fields: dict[str, Any] = {
        "insurer": "Suraksha Health Insurance Co. (fictional)",
        "product": "Parivar Suraksha Floater",
        "sum_insured": rupees(500_000),
        "continuous_cover_months": 24,
    }
    fields.update(overrides)
    return Policy(**fields)


def facts(
    *lines: BillLine,
    mode: ClaimMode = ClaimMode.PRE_SUBMISSION,
    policy_: Policy | None = None,
    letter: InsurerLetter | None = None,
    documents: tuple[DocumentKind, ...] = ALL_DOCUMENTS,
    admission: Admission | None = None,
    hospital: Hospital | None = None,
) -> ClaimFacts:
    return ClaimFacts(
        claim_id="ARZ-TEST-0001",
        mode=mode,
        hospital=hospital or Hospital(name="Sanjeevani Multispeciality Hospital", city="Vadodara"),
        patient=Patient(redacted_id="P-7F3A", age=58),
        policy=policy_ or policy(),
        admission=admission or Admission(),
        bill_lines=lines,
        insurer_letter=letter,
        documents_present=documents,
    )
