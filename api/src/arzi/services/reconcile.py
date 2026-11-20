"""Turn redacted transcriptions into engine-ready ``ClaimFacts``, deterministically.

The model copied strings; this module parses them (amounts to paise, dates, percentages), checks
them (line sum against the printed total, confidence) and maps them (letter rows to bill lines).
Anything it cannot settle becomes a ``ReviewIssue`` for a person, never a guess.
"""

import datetime as dt
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from arzi.domain.enums import (
    ClaimMode,
    CopayBase,
    DeductionReason,
    DocumentKind,
    InsurerLetterType,
    RejectionGround,
    RoomRentCapType,
)
from arzi.domain.models import (
    Admission,
    BillLine,
    CategoryCap,
    ClaimFacts,
    Copay,
    Hospital,
    IcuCap,
    InsurerDeduction,
    InsurerLetter,
    Patient,
    PctOfSumInsuredCap,
    PerDayAmountCap,
    Policy,
    PolicyClause,
    ReviewIssue,
    RoomRentCap,
    SubLimit,
    WaitingCondition,
)
from arzi.domain.money import MoneyParseError, Paise, format_inr, to_paise, total
from arzi.rules.matching import THRESHOLD, coverage_score, normalise
from arzi.services.errors import AppError
from arzi.services.extraction_schemas import (
    BillExtraction,
    CopayBaseText,
    DischargeExtraction,
    DocType,
    InsurerLetterExtraction,
    PolicyExtraction,
    RoomRentCapKind,
    WaitingText,
)

LOW_CONFIDENCE = 0.8
_MARKED = r"(?:₹|\bRs\.?|\bINR)\s*\d[\d,]*(?:\.\d+)?"
_MARKED_AMOUNT = re.compile(_MARKED, re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)")
_DATE_FORMATS = ("%Y-%m-%d", "%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y")

DOCUMENT_KINDS = {
    DocType.POLICY_SCHEDULE: DocumentKind.POLICY,
    DocType.POLICY_WORDING: DocumentKind.POLICY,
    DocType.ITEMISED_BILL: DocumentKind.ITEMISED_BILL,
    DocType.DISCHARGE_SUMMARY: DocumentKind.DISCHARGE_SUMMARY,
    DocType.INVESTIGATION_REPORT: DocumentKind.INVESTIGATION_REPORTS,
    DocType.IMPLANT_INVOICE: DocumentKind.IMPLANT_INVOICE,
    DocType.INSURER_LETTER: DocumentKind.INSURER_LETTER,
}


class FactsIncompleteError(AppError):
    status, slug = 422, "facts-incomplete"


@dataclass
class ReconcileInput:
    claim_id: str
    mode: ClaimMode
    hospital: Hospital
    patient_pseudonym: str
    document_types: Sequence[DocType]
    policies: Sequence[PolicyExtraction] = ()
    bills: Sequence[BillExtraction] = ()
    discharges: Sequence[DischargeExtraction] = ()
    letters: Sequence[InsurerLetterExtraction] = ()


@dataclass
class ReconcileOutcome:
    facts: ClaimFacts
    issues: list[ReviewIssue] = field(default_factory=list)


class _Issues(list[ReviewIssue]):
    def add(self, code: str, message: str, line_id: int | None = None) -> None:
        self.append(
            ReviewIssue.model_validate({"code": code, "message": message, "line_id": line_id})
        )


def reconcile(data: ReconcileInput) -> ReconcileOutcome:
    issues = _Issues()
    if not data.bills:
        raise FactsIncompleteError("No itemised bill was found among the documents.")
    lines = _bill_lines(data.bills, issues)
    if not lines:
        raise FactsIncompleteError("No bill line could be read.")
    admission = _admission(data.discharges, data.bills)
    policy = _policy(data.policies, admission, data.hospital, issues)
    letter = (
        _letter(data.letters, lines, issues) if data.mode is not ClaimMode.PRE_SUBMISSION else None
    )
    if data.mode is not ClaimMode.PRE_SUBMISSION and letter is None:
        raise FactsIncompleteError("This claim needs the insurer's letter.")
    present = tuple(
        dict.fromkeys(DOCUMENT_KINDS[t] for t in data.document_types if t in DOCUMENT_KINDS)
    )
    age = _first([*(d.patient_age for d in data.discharges), *(b.patient_age for b in data.bills)])
    facts = ClaimFacts(
        claim_id=data.claim_id,
        mode=data.mode,
        hospital=data.hospital,
        patient=Patient(redacted_id=data.patient_pseudonym, age=age),
        policy=policy,
        admission=admission,
        bill_lines=tuple(lines),
        insurer_letter=letter,
        documents_present=present,
    )
    return ReconcileOutcome(facts=facts, issues=list(issues))


# --------------------------------------------------------------------------- parsing helpers


def _first[T](values: Iterable[T | None]) -> T | None:
    return next((v for v in values if v is not None), None)


def parse_date(text: str | None) -> dt.date | None:
    if not text:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def months_between(start: dt.date, end: dt.date) -> int:
    """Completed months of continuous cover from ``start`` to ``end``."""
    months = (end.year - start.year) * 12 + (end.month - start.month)
    return max(0, months - (1 if end.day < start.day else 0))


def _amount(text: str | None) -> Paise | None:
    """A printed amount, also when it sits in words ("Rs. 40,000.00 per eye").

    Inside surrounding words only a figure marked as money (₹, Rs or INR) counts, so the "1"
    of "1% of sum insured" is never read as one rupee.
    """
    if text is None:
        return None
    try:
        return to_paise(text)
    except MoneyParseError:
        pass
    match = _MARKED_AMOUNT.search(text)
    if match is None:
        return None
    try:
        return to_paise(match.group(0))
    except MoneyParseError:  # pragma: no cover - the pattern admits only plain amounts
        return None


def _percent(text: str | None) -> Decimal | None:
    match = _PERCENT.search(text or "")
    if not match:
        return None
    try:
        value = Decimal(match.group(1))
    except InvalidOperation:  # pragma: no cover - the regex admits only decimal numbers
        return None
    return value if 0 <= value <= 100 else None


def _quantity(text: str) -> Decimal | None:
    try:
        value = Decimal(text.replace(",", "").strip())
    except InvalidOperation:
        return None
    return value if value > 0 else None


# --------------------------------------------------------------------------- bill


def _bill_lines(bills: Sequence[BillExtraction], issues: _Issues) -> list[BillLine]:
    bill = max(bills, key=lambda b: len(b.lines))
    lines: list[BillLine] = []
    for number, row in enumerate(bill.lines, start=1):
        amount = _amount(row.amount)
        if amount is None:
            issues.add("unreadable_amount", f"Line {number}: the amount could not be read.", number)
            continue
        qty = _quantity(row.qty)
        if qty is None:
            issues.add(
                "unreadable_amount",
                f"Line {number}: the quantity could not be read; 1 assumed.",
                number,
            )
        lines.append(
            BillLine(
                line_id=number,
                description=row.description.strip() or f"Line {number}",
                category=row.category,
                amount=amount,
                qty=qty or Decimal(1),
                source_page=row.page,
                confidence=row.confidence,
            )
        )
        if row.confidence < LOW_CONFIDENCE:
            issues.add("low_confidence_line", f"Line {number}: please confirm this line.", number)
    printed = _amount(bill.printed_total)
    computed = total(line.amount for line in lines)
    if printed is not None and printed != computed:
        issues.add(
            "total_mismatch",
            f"Lines add up to {format_inr(computed)} but the bill prints {format_inr(printed)}.",
        )
    return lines


def _admission(
    discharges: Sequence[DischargeExtraction], bills: Sequence[BillExtraction]
) -> Admission:
    d = discharges[0] if discharges else None
    b = bills[0]
    date_in = parse_date(_first([d.admission_date if d else None, b.admission_date]))
    date_out = parse_date(_first([d.discharge_date if d else None, b.discharge_date]))
    if date_in and date_out and date_out < date_in:
        date_out = None
    return Admission(
        date_in=date_in,
        date_out=date_out,
        diagnosis=(d.diagnosis if d else None) or "",
        procedure=(d.procedure if d else None) or "",
        icd10=d.icd10 if d else None,
        room_category_used=_first([d.room_category if d else None, b.room_category]),
    )


# --------------------------------------------------------------------------- policy


def _merge_policies(policies: Sequence[PolicyExtraction]) -> PolicyExtraction:
    merged: dict[str, object] = {}
    for policy in policies:
        for name, value in policy:
            if isinstance(value, list):
                existing = merged.setdefault(name, [])
                assert isinstance(existing, list)  # noqa: S101 - same field, same type
                existing.extend(v for v in value if v not in existing)
            elif merged.get(name) is None:
                merged[name] = value
    return PolicyExtraction.model_validate(merged)


def _policy(
    policies: Sequence[PolicyExtraction], admission: Admission, hospital: Hospital, issues: _Issues
) -> Policy:
    p = _merge_policies(policies) if policies else PolicyExtraction()
    if not policies:
        issues.add("missing_document", "No policy document was found; limits are unknown.")
    sum_insured = _amount(p.sum_insured)
    if sum_insured is None:
        issues.add("missing_field", "The sum insured could not be read.")
    inception = parse_date(p.first_inception_date)
    cover = 0
    if inception and admission.date_in:
        cover = months_between(inception, admission.date_in)
    else:
        issues.add(
            "missing_field",
            "Continuous cover could not be worked out (inception or admission date missing).",
        )
    clauses = tuple(
        PolicyClause(id=c.id.strip(), title=c.title.strip(), text=c.text.strip(), page=c.page)
        for c in {c.id.strip(): c for c in p.clauses}.values()
    )
    return Policy(
        insurer=p.insurer or "Unknown insurer",
        product=p.product or "",
        sum_insured=sum_insured or Paise(0),
        continuous_cover_months=cover,
        room_rent_cap=_room_cap(p, hospital, issues),
        proportionate_clause_id=_clause_titled(clauses, "proportionate"),
        icu_cap=_icu_cap(p, issues),
        copay=_copay(p, issues),
        ped_declared=_waiting(p.ped_declared),
        specific_waiting=_waiting(p.specific_waiting),
        sub_limits=_sub_limits(p, issues),
        non_payable_addon=bool(p.non_medical_cover_opted),
        claims_clause_id=_clause_titled(clauses, "document"),
        clauses=clauses,
    )


def _clause_titled(clauses: Sequence[PolicyClause], word: str) -> str | None:
    return next((c.id for c in clauses if word in c.title.lower()), None)


def _room_cap(p: PolicyExtraction, hospital: Hospital, issues: _Issues) -> RoomRentCap | None:
    cap = p.room_rent_cap
    if cap is None or cap.kind is RoomRentCapKind.NO_LIMIT:
        return None
    if cap.kind is RoomRentCapKind.PER_DAY_AMOUNT and (amount := _amount(cap.amount)) is not None:
        return PerDayAmountCap(
            type=RoomRentCapType.PER_DAY_AMOUNT, amount=amount, clause_id=cap.clause
        )
    if (
        cap.kind is RoomRentCapKind.PCT_OF_SUM_INSURED
        and (pct := _percent(cap.percent)) is not None
    ):
        return PctOfSumInsuredCap(type=RoomRentCapType.PCT_OF_SI, pct=pct, clause_id=cap.clause)
    if cap.kind is RoomRentCapKind.ROOM_CATEGORY and cap.category:
        return CategoryCap(
            type=RoomRentCapType.CATEGORY, category=cap.category, clause_id=cap.clause
        )
    issues.add("cap_unresolved", "The room-rent limit could not be read; room checks are skipped.")
    return None


def _icu_cap(p: PolicyExtraction, issues: _Issues) -> IcuCap | None:
    if not p.icu_cap_per_day:
        return None
    amount = _amount(p.icu_cap_per_day)
    if amount is None:
        return None  # "No limit (actual charges)" and similar wording
    clause = _first(c.id for c in p.clauses if "icu" in c.title.lower())
    return IcuCap(amount_per_day=amount, clause_id=clause)


def _copay(p: PolicyExtraction, issues: _Issues) -> Copay | None:
    if p.copay is None or not p.copay.percent:
        return None
    pct = _percent(p.copay.percent)
    if pct is None:
        issues.add("missing_field", "The co-payment percentage could not be read.")
        return None
    base = (
        CopayBase.CLAIMED if p.copay.applies_to is CopayBaseText.CLAIMED else CopayBase.ADMISSIBLE
    )
    return Copay(pct=pct, base=base, clause_id=p.copay.clause)


def _waiting(rows: Sequence[WaitingText]) -> tuple[WaitingCondition, ...]:
    return tuple(
        WaitingCondition(condition=r.condition.strip(), waiting_months=r.months, clause_id=r.clause)
        for r in rows
        if r.condition.strip()
    )


def _sub_limits(p: PolicyExtraction, issues: _Issues) -> tuple[SubLimit, ...]:
    limits = []
    for row in p.sub_limits:
        amount = _amount(row.limit)
        if amount is None:
            issues.add("missing_field", f"The sub-limit for '{row.item}' could not be read.")
            continue
        limits.append(SubLimit(item=row.item.strip(), limit=amount, clause_id=row.clause))
    return tuple(limits)


# --------------------------------------------------------------------------- insurer letter

_REASONS = {code.value: DeductionReason(code.value) for code in DeductionReason}
_GROUNDS = {code.value: RejectionGround(code.value) for code in RejectionGround}
_CLAIM_LEVEL = {"claim level", "claim", "overall", "total"}


def match_line(text: str, lines: Sequence[BillLine]) -> int | None:
    """The bill line a letter row refers to.

    Exact normalised text first. Otherwise a fuzzy match in either direction (letters often
    abbreviate "Laundry charges" to "Laundry"), accepted only when exactly one line fits, so a
    vague row such as "Charges" is reported for review rather than pinned to a guess.
    """
    wanted = normalise(text)
    for line in lines:
        if normalise(line.description) == wanted:
            return line.line_id
    candidates = []
    for line in lines:
        theirs = normalise(line.description)
        if max(coverage_score(wanted, theirs), coverage_score(theirs, wanted)) >= THRESHOLD:
            candidates.append(line.line_id)
    return candidates[0] if len(candidates) == 1 else None


def _letter(
    letters: Sequence[InsurerLetterExtraction], lines: Sequence[BillLine], issues: _Issues
) -> InsurerLetter | None:
    if not letters:
        return None
    x = letters[0]
    deductions = []
    for row in x.deductions:
        amount = _amount(row.deducted)
        if amount is None:
            issues.add("unreadable_amount", f"A deduction for '{row.bill_item}' could not be read.")
            continue
        line_id = None
        if row.bill_item.strip().lower() not in _CLAIM_LEVEL:
            line_id = match_line(row.bill_item, lines)
            if line_id is None:
                issues.add(
                    "unmapped_deduction", f"'{row.bill_item}' in the letter matches no bill line."
                )
        deductions.append(
            InsurerDeduction(
                line_id=line_id,
                amount=amount,
                reason=_REASONS[row.reason_code.value],
                reason_text=row.reason,
                clause_cited=row.clause,
            )
        )
    kind = InsurerLetterType(x.kind.value)
    ground = _GROUNDS[x.rejection_code.value] if x.rejection_code else None
    if kind is InsurerLetterType.REJECTION and ground is None:
        ground = RejectionGround.OTHER
    claimed = _amount(x.amount_claimed)
    if claimed is None:
        issues.add("missing_field", "The claimed amount in the insurer's letter could not be read.")
    return InsurerLetter(
        type=kind,
        date=parse_date(x.letter_date),
        amount_claimed=claimed or total(line.amount for line in lines),
        amount_approved=_amount(x.amount_approved) or Paise(0),
        deductions=tuple(deductions),
        rejection_ground=ground,
        fraud_alleged=x.fraud_alleged,
    )
