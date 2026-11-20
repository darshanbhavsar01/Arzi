"""The three demo cases: one definition per case drives facts.json, expected.json and every PDF.

Everything here is synthetic. Organisations are fictional and marked so. People's names come
from a fixed list of common Gujarati names; phone numbers use Arzi's test pattern
+91 99999 0XXXX; Aadhaar-like numbers deliberately fail the Verhoeff check; emails use the
reserved example.com domain. These identifiers exist only so the redaction step has
something realistic to remove.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from arzi.domain.enums import (
    ClaimMode,
    CopayBase,
    DeductionReason,
    DocumentKind,
    InsurerLetterType,
    LineCategory,
    RejectionGround,
    RoomRentCapType,
)
from arzi.domain.models import (
    Admission,
    BillLine,
    ClaimFacts,
    Copay,
    Hospital,
    InsurerDeduction,
    InsurerLetter,
    Patient,
    PctOfSumInsuredCap,
    PerDayAmountCap,
    Policy,
    PolicyClause,
    RoomCategory,
    SubLimit,
    WaitingCondition,
)
from arzi.domain.money import rupees

C = LineCategory
D = DeductionReason

HOSPITAL_NAME = "Sanjeevani Multispeciality Hospital"
HOSPITAL_ADDRESS = "Plot 18, Sanjeevani Marg (fictional), Satellite, Ahmedabad 380015"
HOSPITAL_PHONE = "+91 99999 00100"
INSURER_NAME = "Suraksha Health Insurance Co. (fictional)"
INSURER_ADDRESS = "Suraksha Bhavan (fictional), Ashram Road, Ahmedabad 380009"
PRODUCT = "Parivar Suraksha Floater (fictional)"

# --------------------------------------------------------------------------- Verhoeff

_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)
_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)
_INV = (0, 4, 3, 2, 1, 5, 6, 7, 8, 9)


def verhoeff_valid(number: str) -> bool:
    check = 0
    for i, digit in enumerate(reversed(number.replace(" ", ""))):
        check = _D[check][_P[i % 8][int(digit)]]
    return check == 0


def aadhaar_like(eleven_digits: str) -> str:
    """Twelve digits shaped like an Aadhaar number whose check digit is deliberately wrong."""
    check = 0
    for i, digit in enumerate(reversed(eleven_digits)):
        check = _D[check][_P[(i + 1) % 8][int(digit)]]
    wrong = (_INV[check] + 1) % 10
    digits = f"{eleven_digits}{wrong}"
    return f"{digits[:4]} {digits[4:8]} {digits[8:]}"


# --------------------------------------------------------------------------- people


@dataclass(frozen=True)
class Person:
    name: str
    age: int
    sex: str
    phone: str
    aadhaar_like: str
    pan_like: str
    email: str
    address: str


@dataclass(frozen=True)
class Implant:
    name: str
    vendor: str
    catalogue_no: str
    lot_no: str


@dataclass(frozen=True)
class DemoCase:
    slug: str
    title: str
    story: str
    facts: ClaimFacts
    patient: Person
    uhid: str
    ip_number: str
    policy_number: str
    member_id: str
    claim_number: str
    first_inception: date
    period_start: date
    period_end: date
    consultant: str
    course: str
    investigations: tuple[tuple[str, str, str], ...]
    implant: Implant
    scanned_bill: bool = False

    def identifiers(self) -> dict[str, str]:
        """Every synthetic identifier printed on this case's documents, by kind."""
        p = self.patient
        identifiers = {
            "patient_name": p.name,
            "phone": p.phone,
            "aadhaar_like": p.aadhaar_like,
            "pan_like": p.pan_like,
            "email": p.email,
            "address": p.address,
            "policy_number": self.policy_number,
            "member_id": self.member_id,
            "uhid": self.uhid,
            "ip_number": self.ip_number,
        }
        if self.facts.insurer_letter is not None:  # the claim number is only on its letter
            identifiers["claim_number"] = self.claim_number
        return identifiers


# --------------------------------------------------------------------------- policy


CLAUSES = (
    PolicyClause(
        id="4.2",
        title="Room rent",
        text=(
            "Room, boarding and nursing charges are payable up to the room-rent limit shown in "
            "the Policy Schedule for each day of hospitalisation. Charges above the limit are "
            "borne by the insured person."
        ),
        page=1,
    ),
    PolicyClause(
        id="4.3",
        title="Proportionate deduction",
        text=(
            "If the insured person occupies a room above the eligible limit, associated medical "
            "expenses are payable in the proportion that the eligible room rent bears to the room "
            "rent actually charged. Associated medical expenses do not include pharmacy and "
            "consumables, implants and medical devices, and diagnostics, and no proportionate "
            "deduction applies to ICU charges."
        ),
        page=1,
    ),
    PolicyClause(
        id="4.4",
        title="ICU charges",
        text="Intensive care unit charges are payable up to the ICU limit shown in the Policy "
        "Schedule, if any.",
        page=1,
    ),
    PolicyClause(
        id="5.1",
        title="Pre-existing diseases",
        text=(
            "Expenses related to a pre-existing disease declared in the proposal are covered after "
            "the waiting period stated in the Policy Schedule of continuous coverage since the "
            "first policy with the Company."
        ),
        page=2,
    ),
    PolicyClause(
        id="5.2",
        title="Specific waiting periods",
        text="Treatment of the conditions listed in the Policy Schedule is covered after the "
        "stated waiting period of continuous coverage.",
        page=2,
    ),
    PolicyClause(
        id="6.1",
        title="Sub-limits",
        text="Payment for the procedures listed in the Policy Schedule is limited to the amount "
        "stated against each procedure.",
        page=2,
    ),
    PolicyClause(
        id="7.4",
        title="Co-payment",
        text="Each admissible claim is subject to the co-payment percentage stated in the Policy "
        "Schedule, applied on the admissible claim amount.",
        page=3,
    ),
    PolicyClause(
        id="8.1",
        title="Non-medical expenses",
        text="Items listed as not payable in the list of non-medical expenses annexed to this "
        "policy are not payable unless an optional cover for them is in force.",
        page=3,
    ),
    PolicyClause(
        id="9.2",
        title="Claim documents",
        text=(
            "Claims must be supported by the discharge summary, the final itemised bill, "
            "investigation reports and, where an implant is used, the implant invoice and sticker."
        ),
        page=3,
    ),
)

# Shared wording and limits; each case sets its own cover, caps and co-pay.
_BASE_POLICY = Policy(
    insurer=INSURER_NAME,
    product=PRODUCT,
    sum_insured=rupees(500_000),
    proportionate_clause_id="4.3",
    claims_clause_id="9.2",
    specific_waiting=(
        WaitingCondition(condition="Cataract", waiting_months=24, clause_id="5.2"),
        WaitingCondition(condition="Hernia", waiting_months=24, clause_id="5.2"),
    ),
    sub_limits=(SubLimit(item="Cataract", limit=rupees(40_000), clause_id="6.1"),),
    clauses=CLAUSES,
    continuous_cover_months=0,
)

HOSPITAL = Hospital(
    name=HOSPITAL_NAME,
    city="Ahmedabad",
    room_categories=(
        RoomCategory(name="General ward", rate_per_day=rupees(2_500)),
        RoomCategory(name="Twin sharing", rate_per_day=rupees(4_500)),
        RoomCategory(name="Single private AC", rate_per_day=rupees(8_000)),
    ),
)

ALL_CLAIM_DOCUMENTS = (
    DocumentKind.POLICY,
    DocumentKind.ITEMISED_BILL,
    DocumentKind.DISCHARGE_SUMMARY,
    DocumentKind.INVESTIGATION_REPORTS,
    DocumentKind.IMPLANT_INVOICE,
)


def _line(
    line_id: int, category: LineCategory, amount: int, description: str, qty: int = 1, page: int = 1
) -> BillLine:
    return BillLine(
        line_id=line_id,
        description=description,
        category=category,
        amount=rupees(amount),
        qty=Decimal(qty),
        source_page=page,
        confidence=1.0,
    )


# --------------------------------------------------------------------------- case A

_HIP_LINES = (
    _line(1, C.ROOM, 32_000, "Single private AC room", qty=4),
    _line(2, C.ICU, 15_000, "ICU charges"),
    _line(3, C.SURGEON, 60_000, "Surgeon fees"),
    _line(4, C.OT, 25_000, "Operation theatre charges"),
    _line(5, C.NURSING, 8_000, "Nursing charges"),
    _line(6, C.PHARMACY, 30_000, "Pharmacy and medicines"),
    _line(7, C.DIAGNOSTICS, 12_000, "Laboratory and radiology"),
    _line(8, C.IMPLANT, 40_000, "Bipolar hip prosthesis (implant)"),
    _line(9, C.NON_PAYABLE, 1_200, "Laundry charges"),
    _line(10, C.NON_PAYABLE, 800, "Cold pack / hot pack"),
    _line(11, C.NON_PAYABLE, 1_500, "Crepe bandage"),
)
_HIP_POLICY = _BASE_POLICY.model_copy(
    update={
        "continuous_cover_months": 30,
        "room_rent_cap": PerDayAmountCap(
            type=RoomRentCapType.PER_DAY_AMOUNT, amount=rupees(5_000), clause_id="4.2"
        ),
        "copay": Copay(pct=Decimal(10), base=CopayBase.ADMISSIBLE, clause_id="7.4"),
    }
)
_HIP_ADMISSION = Admission(
    date_in=date(2026, 10, 12),
    date_out=date(2026, 10, 17),
    diagnosis="Fracture of neck of right femur",
    procedure="Right hip hemiarthroplasty",
    icd10="S72.0",
    room_category_used="Single private AC",
)
_HIP_COURSE = (
    "Admitted after a fall at home with pain and inability to bear weight on the right leg. "
    "X-ray confirmed a displaced fracture of the neck of the right femur. Right hip "
    "hemiarthroplasty with a bipolar prosthesis was done under spinal anaesthesia on day 2. "
    "Observed in ICU for one day after surgery, then shifted to the room. Mobilised with a "
    "walker from day 3. Wound healthy at discharge."
)
_HIP_INVESTIGATIONS = (
    ("Haemoglobin", "11.8 g/dL", "12.0 - 15.0"),
    ("Total leucocyte count", "9,400 /cumm", "4,000 - 11,000"),
    ("Serum creatinine", "0.9 mg/dL", "0.6 - 1.2"),
    ("X-ray right hip (AP)", "Displaced fracture neck of femur", "-"),
)
_HIP_IMPLANT = Implant(
    name="Bipolar hip prosthesis, cemented",
    vendor="Arogya Ortho Devices Pvt. Ltd. (fictional)",
    catalogue_no="AOD-BHP-46",
    lot_no="LOT 26A0912",
)

CASE_A = DemoCase(
    slug="case_a",
    title="Pre-submission audit",
    story=(
        "Before filing, the billing desk sees ₹67,887.50 at risk across four flags and learns "
        "that moving the patient to an eligible room, or taking written upgrade consent, avoids "
        "₹46,875 of it."
    ),
    facts=ClaimFacts(
        claim_id="ARZ-2026-0001",
        mode=ClaimMode.PRE_SUBMISSION,
        hospital=HOSPITAL,
        patient=Patient(redacted_id="P-7F3A", age=67),
        policy=_HIP_POLICY,
        admission=_HIP_ADMISSION,
        bill_lines=_HIP_LINES,
        documents_present=ALL_CLAIM_DOCUMENTS,
    ),
    patient=Person(
        name="Ramesh Kantilal Parmar",
        age=67,
        sex="Male",
        phone="+91 99999 01234",
        aadhaar_like=aadhaar_like("73519284061"),
        pan_like="ZQXPP4821K",
        email="ramesh.parmar@example.com",
        address="B-14, Shantivan Society (fictional), Vastrapur, Ahmedabad 380015",
    ),
    uhid="SMH-UHID-0417",
    ip_number="IP/2026/10/0731",
    policy_number="SHI/PSF/2026/004417",
    member_id="SHI-M-0441701",
    claim_number="CL-2026-118204",
    first_inception=date(2024, 4, 12),
    period_start=date(2026, 4, 12),
    period_end=date(2027, 4, 11),
    consultant="Dr. Anil Mehta, MS (Ortho)",
    course=_HIP_COURSE,
    investigations=_HIP_INVESTIGATIONS,
    implant=_HIP_IMPLANT,
    scanned_bill=True,
)

# --------------------------------------------------------------------------- case B

_B_LINES = (*_HIP_LINES, _line(12, C.OTHER, 1_000, "Registration charges"))


def _cut(
    line_id: int | None, amount: int, reason: DeductionReason, text: str, clause: str
) -> InsurerDeduction:
    return InsurerDeduction(
        line_id=line_id, amount=rupees(amount), reason=reason, reason_text=text, clause_cited=clause
    )


_B_LETTER = InsurerLetter(
    type=InsurerLetterType.DEDUCTION,
    date=date(2026, 11, 2),
    amount_claimed=rupees(226_500),
    amount_approved=rupees(138_375),
    deductions=(
        _cut(1, 12_000, D.ROOM_RENT_EXCESS, "Room rent above eligible limit", "4.2"),
        _cut(2, 5_625, D.PROPORTIONATE, "Proportionate deduction", "4.3"),
        _cut(3, 22_500, D.PROPORTIONATE, "Proportionate deduction", "4.3"),
        _cut(4, 9_375, D.PROPORTIONATE, "Proportionate deduction", "4.3"),
        _cut(5, 3_000, D.PROPORTIONATE, "Proportionate deduction", "4.3"),
        _cut(6, 11_250, D.PROPORTIONATE, "Proportionate deduction", "4.3"),
        _cut(7, 4_500, D.PROPORTIONATE, "Proportionate deduction", "4.3"),
        _cut(9, 1_200, D.NON_PAYABLE, "Non-medical expense", "8.1"),
        _cut(10, 800, D.NON_PAYABLE, "Non-medical expense", "8.1"),
        _cut(11, 1_500, D.NON_PAYABLE, "Non-medical expense", "8.1"),
        _cut(12, 1_000, D.NON_PAYABLE, "Registration charges not payable", "8.1"),
        _cut(None, 15_375, D.COPAY, "Co-payment 10%", "7.4"),
    ),
)

CASE_B = DemoCase(
    slug="case_b",
    title="Deduction appeal",
    story=(
        "The insurer prorated pharmacy, diagnostics and ICU and deducted registration charges "
        "separately. Arzi finds ₹20,137.50 recoverable and drafts a clause-cited appeal to the "
        "insurer's Grievance Redressal Officer for a human to review and sign."
    ),
    facts=ClaimFacts(
        claim_id="ARZ-2026-0002",
        mode=ClaimMode.POST_DEDUCTION,
        hospital=HOSPITAL,
        patient=Patient(redacted_id="P-2C91", age=54),
        policy=_HIP_POLICY,
        admission=_HIP_ADMISSION.model_copy(
            update={"date_in": date(2026, 10, 3), "date_out": date(2026, 10, 8)}
        ),
        bill_lines=_B_LINES,
        insurer_letter=_B_LETTER,
        documents_present=(*ALL_CLAIM_DOCUMENTS, DocumentKind.INSURER_LETTER),
    ),
    patient=Person(
        name="Hemlata Dilip Joshi",
        age=54,
        sex="Female",
        phone="+91 99999 02468",
        aadhaar_like=aadhaar_like("84620175394"),
        pan_like="ZQXPJ7364M",
        email="hemlata.joshi@example.com",
        address="12, Gulmohar Park (fictional), Maninagar, Ahmedabad 380008",
    ),
    uhid="SMH-UHID-0388",
    ip_number="IP/2026/10/0652",
    policy_number="SHI/PSF/2026/003881",
    member_id="SHI-M-0388102",
    claim_number="CL-2026-117655",
    first_inception=date(2024, 4, 3),
    period_start=date(2026, 4, 3),
    period_end=date(2027, 4, 2),
    consultant="Dr. Anil Mehta, MS (Ortho)",
    course=_HIP_COURSE,
    investigations=_HIP_INVESTIGATIONS,
    implant=_HIP_IMPLANT,
)

# --------------------------------------------------------------------------- case C

_KNEE_LINES = (
    _line(1, C.ROOM, 18_000, "Twin sharing room", qty=4),
    _line(2, C.SURGEON, 90_000, "Surgeon fees"),
    _line(3, C.ANAESTHETIST, 20_000, "Anaesthetist fees"),
    _line(4, C.OT, 30_000, "Operation theatre charges"),
    _line(5, C.NURSING, 6_000, "Nursing charges"),
    _line(6, C.PHARMACY, 22_000, "Pharmacy and medicines"),
    _line(7, C.DIAGNOSTICS, 9_000, "Laboratory and radiology"),
    _line(8, C.IMPLANT, 110_000, "Total knee prosthesis (implant)"),
    _line(9, C.OTHER, 5_000, "Physiotherapy sessions"),
)

CASE_C = DemoCase(
    slug="case_c",
    title="Rejection appeal",
    story=(
        "A knee replacement was rejected for the pre-existing disease waiting period. The policy "
        "has 40 months of continuous cover against a 36-month maximum waiting period, so the "
        "rejection does not hold. Arzi drafts the appeal and explains it to the family in "
        "Gujarati."
    ),
    facts=ClaimFacts(
        claim_id="ARZ-2026-0003",
        mode=ClaimMode.POST_REJECTION,
        hospital=HOSPITAL,
        patient=Patient(redacted_id="P-91D4", age=63),
        policy=_BASE_POLICY.model_copy(
            update={
                "continuous_cover_months": 40,
                "room_rent_cap": PctOfSumInsuredCap(
                    type=RoomRentCapType.PCT_OF_SI, pct=Decimal(1), clause_id="4.2"
                ),
                "ped_declared": (
                    WaitingCondition(
                        condition="Osteoarthritis of knee", waiting_months=36, clause_id="5.1"
                    ),
                ),
            }
        ),
        admission=Admission(
            date_in=date(2026, 10, 20),
            date_out=date(2026, 10, 24),
            diagnosis="Primary osteoarthritis, right knee",
            procedure="Right total knee replacement",
            icd10="M17.1",
            room_category_used="Twin sharing",
        ),
        bill_lines=_KNEE_LINES,
        insurer_letter=InsurerLetter(
            type=InsurerLetterType.REJECTION,
            date=date(2026, 11, 4),
            amount_claimed=rupees(310_000),
            amount_approved=rupees(0),
            rejection_ground=RejectionGround.PED_WAITING,
        ),
        documents_present=(*ALL_CLAIM_DOCUMENTS, DocumentKind.INSURER_LETTER),
    ),
    patient=Person(
        name="Bhanuben Mahendra Patel",
        age=63,
        sex="Female",
        phone="+91 99999 03579",
        aadhaar_like=aadhaar_like("92736481503"),
        pan_like="ZQXPB2957L",
        email="bhanuben.patel@example.com",
        address="7, Ambika Nagar (fictional), Naranpura, Ahmedabad 380013",
    ),
    uhid="SMH-UHID-0459",
    ip_number="IP/2026/10/0802",
    policy_number="SHI/PSF/2026/002236",
    member_id="SHI-M-0223603",
    claim_number="CL-2026-118957",
    first_inception=date(2023, 6, 20),
    period_start=date(2026, 6, 20),
    period_end=date(2027, 6, 19),
    consultant="Dr. Kavita Shah, MS (Ortho)",
    course=(
        "Known case of osteoarthritis of both knees for four years, declared at policy "
        "inception, with progressive pain and restricted walking despite medicines and "
        "physiotherapy. Right total knee replacement was done under spinal anaesthesia on day 1. "
        "Physiotherapy started on day 2; walking with a walker at discharge. Wound healthy."
    ),
    investigations=(
        ("Haemoglobin", "12.6 g/dL", "12.0 - 15.0"),
        ("HbA1c", "5.8 %", "below 5.7"),
        ("Serum creatinine", "0.8 mg/dL", "0.6 - 1.2"),
        ("X-ray right knee (standing)", "Grade IV osteoarthritis", "-"),
    ),
    implant=Implant(
        name="Total knee prosthesis, posterior stabilised",
        vendor="Arogya Ortho Devices Pvt. Ltd. (fictional)",
        catalogue_no="AOD-TKP-PS3",
        lot_no="LOT 26B1407",
    ),
)

CASES = (CASE_A, CASE_B, CASE_C)
