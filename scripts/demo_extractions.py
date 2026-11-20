"""The ideal extraction of each demo document: what a perfect transcription returns.

Built from the same case definition and formatting functions as the PDFs, so every string here is
exactly what is printed on the page. Used by ``fake`` LLM mode, the pipeline integration tests,
and later as the ground truth for extraction evals.
"""

from decimal import Decimal

from demo_data import HOSPITAL_NAME, DemoCase
from demo_documents import money, rs
from pydantic import BaseModel

from arzi.domain.models import PctOfSumInsuredCap, PerDayAmountCap
from arzi.domain.money import Paise, total
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
    PersonIdentifiers,
    PolicyExtraction,
    ReasonCode,
    RejectionCode,
    RoomRentCapKind,
    RoomRentCapText,
    SubLimitText,
    WaitingText,
)

Fixture = tuple[DocType, BaseModel | None]


def _identifiers(case: DemoCase, *fields: str) -> PersonIdentifiers:
    p = case.patient
    values = {
        "patient_name": p.name,
        "phone": p.phone,
        "email": p.email,
        "address": p.address,
        "aadhaar": p.aadhaar_like,
        "pan": p.pan_like,
        "uhid": case.uhid,
        "ip_number": case.ip_number,
        "policy_number": case.policy_number,
        "member_id": case.member_id,
        "claim_number": case.claim_number,
    }
    return PersonIdentifiers.model_validate({f: values[f] for f in fields})


def _schedule(case: DemoCase) -> PolicyExtraction:
    policy = case.facts.policy
    cap = policy.room_rent_cap
    if isinstance(cap, PerDayAmountCap):
        room = RoomRentCapText(
            kind=RoomRentCapKind.PER_DAY_AMOUNT, amount=rs(cap.amount), clause="4.2"
        )
    elif isinstance(cap, PctOfSumInsuredCap):
        room = RoomRentCapText(
            kind=RoomRentCapKind.PCT_OF_SUM_INSURED,
            percent=format(cap.pct.normalize(), "f"),
            clause="4.2",
        )
    else:  # pragma: no cover - the demo cases use the two caps above
        raise ValueError(case.slug)
    copay = policy.copay
    return PolicyExtraction(
        identifiers=_identifiers(
            case, "patient_name", "email", "address", "pan", "policy_number", "member_id"
        ),
        insurer=policy.insurer,
        product=policy.product,
        sum_insured=rs(policy.sum_insured),
        first_inception_date=case.first_inception.isoformat(),
        room_rent_cap=room,
        icu_cap_per_day=None,
        copay=CopayText(percent=format(copay.pct.normalize(), "f"), clause="7.4")
        if copay
        else None,
        sub_limits=[
            SubLimitText(item=s.item, limit=rs(s.limit), clause="6.1") for s in policy.sub_limits
        ],
        specific_waiting=[
            WaitingText(condition=c.condition, months=c.waiting_months, clause="5.2")
            for c in policy.specific_waiting
        ],
        ped_declared=[
            WaitingText(condition=c.condition, months=c.waiting_months, clause="5.1")
            for c in policy.ped_declared
        ],
        non_medical_cover_opted=False,
    )


def _wording(case: DemoCase) -> PolicyExtraction:
    policy = case.facts.policy
    return PolicyExtraction(
        insurer=policy.insurer,
        product=policy.product,
        clauses=[
            ClauseText(id=c.id, title=c.title, text=c.text, page=c.page or 1)
            for c in policy.clauses
        ],
    )


def _bill(case: DemoCase) -> BillExtraction:
    a = case.facts.admission
    lines = case.facts.bill_lines
    return BillExtraction(
        identifiers=_identifiers(
            case, "patient_name", "phone", "address", "uhid", "ip_number", "policy_number"
        ),
        hospital_name=HOSPITAL_NAME,
        patient_age=case.patient.age,
        admission_date=a.date_in.isoformat() if a.date_in else None,
        discharge_date=a.date_out.isoformat() if a.date_out else None,
        room_category=a.room_category_used,
        lines=[
            BillLineText(
                serial=line.line_id,
                description=line.description,
                category=line.category,
                qty=format(line.qty.normalize(), "f"),
                rate=money(_rate(line.amount, line.qty)),
                amount=money(line.amount),
                page=1,
                confidence=0.97,
            )
            for line in lines
        ],
        printed_total=money(total(line.amount for line in lines)),
    )


def _rate(amount: Paise, qty: Decimal) -> Paise:
    numerator, denominator = qty.as_integer_ratio()
    return Paise(amount * denominator // numerator)


def _discharge(case: DemoCase) -> DischargeExtraction:
    a = case.facts.admission
    return DischargeExtraction(
        identifiers=_identifiers(
            case, "patient_name", "phone", "aadhaar", "uhid", "ip_number", "policy_number"
        ),
        patient_age=case.patient.age,
        admission_date=a.date_in.isoformat() if a.date_in else None,
        discharge_date=a.date_out.isoformat() if a.date_out else None,
        diagnosis=a.diagnosis,
        icd10=a.icd10,
        procedure=a.procedure,
        room_category=a.room_category_used,
    )


def _letter(case: DemoCase) -> InsurerLetterExtraction:
    letter = case.facts.insurer_letter
    if letter is None:  # pragma: no cover - only called for cases with a letter
        raise ValueError(case.slug)
    lines = {line.line_id: line.description for line in case.facts.bill_lines}
    identifiers = _identifiers(case, "patient_name", "claim_number", "policy_number", "member_id")
    if letter.rejection_ground is not None:
        return InsurerLetterExtraction(
            identifiers=identifiers,
            kind=LetterKind.REJECTION,
            letter_date=letter.date.isoformat() if letter.date else None,
            amount_claimed=rs(letter.amount_claimed),
            rejection_code=RejectionCode(letter.rejection_ground.value),
            rejection_reason=(
                "The ailment is a pre-existing disease declared at inception and the treatment "
                "falls within the pre-existing disease waiting period under clause 5.1."
            ),
        )
    return InsurerLetterExtraction(
        identifiers=identifiers,
        kind=LetterKind.DEDUCTION,
        letter_date=letter.date.isoformat() if letter.date else None,
        amount_claimed=rs(letter.amount_claimed),
        amount_approved=rs(letter.amount_approved),
        deductions=[
            DeductionText(
                bill_item=lines[d.line_id] if d.line_id is not None else "Claim level",
                deducted=money(d.amount),
                reason=d.reason_text,
                reason_code=ReasonCode(d.reason.value),
                clause=d.clause_cited,
            )
            for d in letter.deductions
        ],
    )


def fixtures(case: DemoCase) -> dict[str, Fixture]:
    """Document file name → (type, ideal extraction or None when only the type matters)."""
    out: dict[str, Fixture] = {
        "policy_schedule.pdf": (DocType.POLICY_SCHEDULE, _schedule(case)),
        "policy_wording_excerpt.pdf": (DocType.POLICY_WORDING, _wording(case)),
        "itemised_bill.pdf": (DocType.ITEMISED_BILL, _bill(case)),
        "discharge_summary.pdf": (DocType.DISCHARGE_SUMMARY, _discharge(case)),
        "investigation_reports.pdf": (DocType.INVESTIGATION_REPORT, None),
        "implant_invoice.pdf": (DocType.IMPLANT_INVOICE, None),
    }
    letter = case.facts.insurer_letter
    if letter is not None:
        name = (
            "insurer_rejection_letter.pdf"
            if letter.rejection_ground
            else "insurer_deduction_letter.pdf"
        )
        out[name] = (DocType.INSURER_LETTER, _letter(case))
    if case.scanned_bill:
        out["bill_scanned.jpg"] = out["itemised_bill.pdf"]
    return out
