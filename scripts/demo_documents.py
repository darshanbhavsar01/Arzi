"""Render the demo case documents as PDFs, plus a scanned-looking JPEG of the bill.

Output is byte-stable: reportlab runs in invariant mode (fixed dates and document IDs), fonts are
the Bitstream Vera TTFs that ship inside reportlab and are embedded, page streams are left
uncompressed (zlib builds differ across platforms), and the scan noise comes from a seeded RNG.
Every page carries a footer saying the document is synthetic.
"""

import random
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium
import reportlab
from demo_data import (
    HOSPITAL_ADDRESS,
    HOSPITAL_NAME,
    HOSPITAL_PHONE,
    INSURER_ADDRESS,
    INSURER_NAME,
    DemoCase,
)
from PIL import Image, ImageChops, ImageFilter
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable

from arzi.domain.enums import LineCategory
from arzi.domain.models import BillLine
from arzi.domain.money import Paise, format_inr, total

FONT, BOLD, ITALIC = "Vera", "Vera-Bold", "Vera-Italic"
_FONT_DIR = Path(reportlab.__file__).parent / "fonts"
for _name, _file in ((FONT, "Vera.ttf"), (BOLD, "VeraBd.ttf"), (ITALIC, "VeraIt.ttf")):
    pdfmetrics.registerFont(TTFont(_name, str(_FONT_DIR / _file)))
pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=BOLD, italic=ITALIC, boldItalic=BOLD)

HOSPITAL_ACCENT = colors.HexColor("#1F6F66")
INSURER_ACCENT = colors.HexColor("#2E3F73")
GRID = colors.HexColor("#B9C0CC")
SHADE = colors.HexColor("#EEF1F5")
FOOTER = "Synthetic test document for Arzi. Fictional organisation and people; not a real record."

BODY = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12)
SMALL = ParagraphStyle("small", parent=BODY, fontSize=7.5, leading=9.5)
H1 = ParagraphStyle("h1", parent=BODY, fontName=BOLD, fontSize=13, leading=16, spaceAfter=4)
H2 = ParagraphStyle("h2", parent=BODY, fontName=BOLD, fontSize=10, leading=13, spaceBefore=6)
RIGHT = ParagraphStyle("right", parent=BODY, alignment=TA_RIGHT)

CATEGORY_LABEL = {
    LineCategory.ROOM: "Room",
    LineCategory.ICU: "ICU",
    LineCategory.SURGEON: "Professional fees",
    LineCategory.ANAESTHETIST: "Professional fees",
    LineCategory.CONSULTATION: "Professional fees",
    LineCategory.OT: "OT charges",
    LineCategory.NURSING: "Nursing",
    LineCategory.PHARMACY: "Pharmacy",
    LineCategory.CONSUMABLE: "Consumables",
    LineCategory.IMPLANT: "Implants",
    LineCategory.DIAGNOSTICS: "Investigations",
    LineCategory.NON_PAYABLE: "Miscellaneous",
    LineCategory.OTHER: "Miscellaneous",
}


# --------------------------------------------------------------------------- formatting


def rs(amount: Paise) -> str:
    """Bill-style amount: ``Rs. 1,57,612.50``."""
    return "Rs. " + money(amount)


def money(amount: Paise) -> str:
    return format_inr(amount, always_paise=True).removeprefix("₹")


def day(value: date | None) -> str:
    return value.strftime("%d-%b-%Y") if value else "-"


_ONES = [
    "Zero",
    "One",
    "Two",
    "Three",
    "Four",
    "Five",
    "Six",
    "Seven",
    "Eight",
    "Nine",
    "Ten",
    "Eleven",
    "Twelve",
    "Thirteen",
    "Fourteen",
    "Fifteen",
    "Sixteen",
    "Seventeen",
    "Eighteen",
    "Nineteen",
]
_TENS = ["_", "_", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]


def _below_hundred(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + (f"-{_ONES[ones]}" if ones else "")


def _below_thousand(n: int) -> str:
    hundreds, rest = divmod(n, 100)
    parts = [f"{_ONES[hundreds]} Hundred"] if hundreds else []
    if rest:
        parts.append(_below_hundred(rest))
    return " ".join(parts)


def in_words(amount: Paise) -> str:
    """Indian numbering in words, as printed on bills: lakh and crore, not million."""
    rupee, paise = divmod(int(amount), 100)
    parts: list[str] = []
    for size, label in ((10**7, "Crore"), (10**5, "Lakh"), (10**3, "Thousand")):
        count, rupee = divmod(rupee, size)
        if count:
            parts.append(f"{_below_thousand(count)} {label}")
    if rupee or not parts:
        parts.append(_below_thousand(rupee) if rupee else "Zero")
    words = "Rupees " + " ".join(parts)
    if paise:
        words += f" and {_below_hundred(paise)} Paise"
    return words + " Only"


# --------------------------------------------------------------------------- page chrome


def _page_painter(org: str, address: str, accent: colors.Color) -> Callable[[Canvas, object], None]:
    def paint(canvas: Canvas, doc: object) -> None:
        width, height = A4
        canvas.saveState()
        canvas.setFillColor(accent)
        canvas.rect(0, height - 6 * mm, width, 6 * mm, stroke=0, fill=1)
        canvas.setFont(BOLD, 14)
        canvas.drawString(18 * mm, height - 17 * mm, org)
        canvas.setFont(FONT, 8)
        canvas.setFillColor(colors.HexColor("#333333"))
        canvas.drawString(18 * mm, height - 22 * mm, address)
        canvas.setStrokeColor(accent)
        canvas.setLineWidth(0.8)
        canvas.line(18 * mm, height - 25 * mm, width - 18 * mm, height - 25 * mm)
        canvas.setFont(ITALIC, 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(18 * mm, 10 * mm, FOOTER)
        canvas.drawRightString(width - 18 * mm, 10 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    return paint


def _build(
    path: Path,
    title: str,
    story: Sequence[Flowable],
    *,
    org: str = HOSPITAL_NAME,
    address: str = f"{HOSPITAL_ADDRESS} · Tel {HOSPITAL_PHONE}",
    accent: colors.Color = HOSPITAL_ACCENT,
) -> None:
    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        title=title,
        author=org,
        subject="Synthetic demo document",
        creator="Arzi demo generator",
        invariant=1,
        pageCompression=0,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=30 * mm,
        bottomMargin=18 * mm,
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates(
        [PageTemplate(id="page", frames=[frame], onPage=_page_painter(org, address, accent))]
    )
    doc.build(list(story))


def _grid(
    rows: Sequence[Sequence[object]],
    widths: Sequence[float],
    *,
    header: bool = True,
    numeric_cols: Sequence[int] = (),
    total_rows: int = 0,
) -> Table:
    table = Table([list(r) for r in rows], colWidths=list(widths), repeatRows=1 if header else 0)
    style: list[tuple[Any, ...]] = [
        ("FONT", (0, 0), (-1, -1), FONT, 8.5),
        ("GRID", (0, 0), (-1, -1), 0.4, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style += [("FONT", (0, 0), (-1, 0), BOLD, 8.5), ("BACKGROUND", (0, 0), (-1, 0), SHADE)]
    style += [("ALIGN", (c, 0), (c, -1), "RIGHT") for c in numeric_cols]
    if total_rows:
        style += [("FONT", (0, -total_rows), (-1, -1), BOLD, 8.5)]
    table.setStyle(TableStyle(style))
    return table


def _fields(pairs: Sequence[tuple[str, str]], columns: int = 2) -> Table:
    """A label/value block, the patient header found on every hospital document."""
    cells = [(Paragraph(f"<b>{k}</b>", SMALL), Paragraph(v, SMALL)) for k, v in pairs]
    rows = []
    for i in range(0, len(cells), columns):
        row: list[object] = []
        for label, value in cells[i : i + columns]:
            row += [label, value]
        row += [""] * (columns * 2 - len(row))
        rows.append(row)
    label_w, value_w = 30 * mm, (174 * mm / columns) - 30 * mm
    table = Table(rows, colWidths=[label_w, value_w] * columns)
    table.setStyle(
        TableStyle(
            [
                ("BOX", (0, 0), (-1, -1), 0.4, GRID),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    return table


def _patient_block(case: DemoCase, *, with_contact: bool = False) -> Table:
    p, a = case.patient, case.facts.admission
    pairs = [
        ("Patient", p.name),
        ("Age / Sex", f"{p.age} years / {p.sex}"),
        ("UHID", case.uhid),
        ("IP number", case.ip_number),
        ("Admitted", day(a.date_in)),
        ("Discharged", day(a.date_out)),
        ("Room category", a.room_category_used or "-"),
        ("Consultant", case.consultant),
        ("Payer", f"{INSURER_NAME}, cashless"),
        ("Policy number", case.policy_number),
    ]
    if with_contact:
        pairs += [("Address", p.address), ("Phone", p.phone)]
    return _fields(pairs)


# --------------------------------------------------------------------------- hospital documents


def _rate(line: BillLine) -> Paise:
    numerator, denominator = line.qty.as_integer_ratio()
    return Paise(line.amount * denominator // numerator)


def itemised_bill(case: DemoCase, path: Path) -> None:
    lines = case.facts.bill_lines
    rows: list[list[object]] = [["S.No.", "Particulars", "Service head", "Qty", "Rate", "Amount"]]
    rows += [
        [
            str(line.line_id),
            line.description,
            CATEGORY_LABEL[line.category],
            format(line.qty.normalize(), "f"),
            money(_rate(line)),
            money(line.amount),
        ]
        for line in lines
    ]
    grand = total(line.amount for line in lines)
    rows.append(["", "Grand total", "", "", "", money(grand)])

    heads: dict[str, Paise] = {}
    for line in lines:
        label = CATEGORY_LABEL[line.category]
        heads[label] = Paise(heads.get(label, 0) + line.amount)
    summary: list[list[object]] = [["Service head", "Amount"]]
    summary += [[label, money(amount)] for label, amount in heads.items()]
    summary += [["Total", money(grand)], ["Less: advance received", money(Paise(0))]]
    summary += [["Net amount (claimed from insurer)", money(grand)]]

    story: list[Flowable] = [
        Paragraph("Final Itemised Bill (In-patient)", H1),
        Paragraph(
            f"Bill number: SMH/IPB/{case.ip_number[-4:]} · "
            f"Bill date: {day(case.facts.admission.date_out)}",
            SMALL,
        ),
        Spacer(1, 4),
        _patient_block(case, with_contact=True),
        Spacer(1, 8),
        _grid(
            rows,
            [12 * mm, 66 * mm, 30 * mm, 12 * mm, 26 * mm, 28 * mm],
            numeric_cols=(3, 4, 5),
            total_rows=1,
        ),
        Spacer(1, 8),
        Paragraph("Summary by service head", H2),
        _grid(summary, [120 * mm, 54 * mm], numeric_cols=(1,), total_rows=3),
        Spacer(1, 6),
        Paragraph(f"<b>Amount in words:</b> {in_words(grand)}", BODY),
        Spacer(1, 4),
        Paragraph("All amounts in Indian Rupees. Rate is per day for room and ICU.", SMALL),
        Spacer(1, 16),
        Paragraph(
            "Billing executive (signature) &nbsp;&nbsp;&nbsp;&nbsp; "
            "Patient / attendant (signature)",
            SMALL,
        ),
    ]
    _build(path, f"Itemised bill {case.ip_number}", story)


def discharge_summary(case: DemoCase, path: Path) -> None:
    a, p = case.facts.admission, case.patient
    story: list[Flowable] = [
        Paragraph("Discharge Summary", H1),
        _patient_block(case),
        Spacer(1, 4),
        _fields([("ID proof", f"Aadhaar {p.aadhaar_like}"), ("Contact", p.phone)]),
        Paragraph("Diagnosis", H2),
        Paragraph(f"{a.diagnosis} (ICD-10 {a.icd10})", BODY),
        Paragraph("Procedure", H2),
        Paragraph(a.procedure, BODY),
        Paragraph("Course in hospital", H2),
        Paragraph(case.course, BODY),
        Paragraph("Condition at discharge", H2),
        Paragraph("Stable. Vitals within normal limits. Pain controlled on oral medicines.", BODY),
        Paragraph("Advice", H2),
        Paragraph(
            "Continue prescribed medicines, physiotherapy as taught, suture removal on day 14, "
            "review in the orthopaedic OPD after two weeks or earlier if fever, wound discharge "
            "or swelling of the leg.",
            BODY,
        ),
        Spacer(1, 18),
        Paragraph(f"{case.consultant}<br/>Consultant, Department of Orthopaedics", BODY),
    ]
    _build(path, f"Discharge summary {case.ip_number}", story)


def investigation_reports(case: DemoCase, path: Path) -> None:
    rows: list[list[object]] = [["Investigation", "Result", "Reference range"]]
    rows += [list(row) for row in case.investigations]
    story: list[Flowable] = [
        Paragraph("Investigation Reports", H1),
        _patient_block(case),
        Spacer(1, 8),
        _grid(rows, [70 * mm, 60 * mm, 44 * mm]),
        Spacer(1, 10),
        Paragraph("Reported by: Department of Laboratory Medicine and Radiology", SMALL),
    ]
    _build(path, f"Investigation reports {case.ip_number}", story)


def implant_invoice(case: DemoCase, path: Path) -> None:
    implant = next(line for line in case.facts.bill_lines if line.category is LineCategory.IMPLANT)
    i = case.implant
    rows: list[list[object]] = [
        ["Item", "Catalogue no.", "Lot / batch", "Qty", "Amount"],
        [i.name, i.catalogue_no, i.lot_no, "1", money(implant.amount)],
        ["Total", "", "", "", money(implant.amount)],
    ]
    story: list[Flowable] = [
        Paragraph("Implant Invoice and Sticker Record", H1),
        Paragraph(f"Supplier: {i.vendor}", BODY),
        Paragraph(
            f"Invoice number: AOD/INV/{case.ip_number[-4:]} · "
            f"Date: {day(case.facts.admission.date_in)}",
            SMALL,
        ),
        Spacer(1, 6),
        _patient_block(case),
        Spacer(1, 8),
        _grid(
            rows, [64 * mm, 30 * mm, 30 * mm, 14 * mm, 36 * mm], numeric_cols=(3, 4), total_rows=1
        ),
        Spacer(1, 8),
        Paragraph(
            f"Implant sticker affixed in the OT register: {i.catalogue_no} / {i.lot_no}", BODY
        ),
    ]
    _build(path, f"Implant invoice {case.ip_number}", story)


# --------------------------------------------------------------------------- insurer documents


def _build_insurer(path: Path, title: str, story: Sequence[Flowable]) -> None:
    _build(path, title, story, org=INSURER_NAME, address=INSURER_ADDRESS, accent=INSURER_ACCENT)


def _room_limit(case: DemoCase) -> str:
    cap = case.facts.policy.room_rent_cap
    amount = getattr(cap, "amount", None)
    if amount is not None:
        return f"{rs(amount)} per day"
    return f"{getattr(cap, 'pct', 0)}% of sum insured per day"


def policy_schedule(case: DemoCase, path: Path) -> None:
    policy, p = case.facts.policy, case.patient
    copay = policy.copay
    ped = ", ".join(f"{c.condition}: {c.waiting_months} months" for c in policy.ped_declared)
    specific = ", ".join(
        f"{c.condition}: {c.waiting_months} months" for c in policy.specific_waiting
    )
    sub_limits = ", ".join(f"{s.item}: {rs(s.limit)} per eye" for s in policy.sub_limits)
    rows: list[list[object]] = [
        ["Item", "Details", "Clause"],
        ["Sum insured (floater)", rs(policy.sum_insured), "-"],
        ["Room rent limit", _room_limit(case), "4.2"],
        ["ICU limit", "No limit (actual charges)", "4.4"],
        [
            "Co-payment",
            f"{copay.pct.normalize():f}% of admissible claim" if copay else "Nil",
            "7.4",
        ],
        ["Sub-limits", sub_limits or "None", "6.1"],
        ["Specific waiting periods", specific or "None", "5.2"],
        ["Pre-existing diseases declared", ped or "None declared", "5.1"],
        ["Non-medical expenses cover", "Not opted", "8.1"],
    ]
    members: list[list[object]] = [
        ["Insured member", "Relation", "Age", "Member ID"],
        [p.name, "Self", str(p.age), case.member_id],
    ]
    story: list[Flowable] = [
        Paragraph("Policy Schedule", H1),
        _fields(
            [
                ("Product", policy.product),
                ("Policy number", case.policy_number),
                ("Period", f"{day(case.period_start)} to {day(case.period_end)}"),
                ("First inception", day(case.first_inception)),
                ("Proposer", p.name),
                ("PAN", p.pan_like),
                ("Email", p.email),
                ("Address", p.address),
            ]
        ),
        Spacer(1, 8),
        _grid(members, [70 * mm, 30 * mm, 20 * mm, 54 * mm]),
        Spacer(1, 8),
        Paragraph("Benefits, limits and waiting periods", H2),
        _grid(rows, [52 * mm, 104 * mm, 18 * mm]),
        Spacer(1, 6),
        Paragraph(
            "Continuous coverage is counted from the first inception date. Read with the policy "
            "wording; clause numbers refer to the wording.",
            SMALL,
        ),
    ]
    _build_insurer(path, f"Policy schedule {case.policy_number}", story)


def policy_wording_excerpt(case: DemoCase, path: Path) -> None:
    story: list[Flowable] = [
        Paragraph(f"{case.facts.policy.product}: Policy Wording (excerpt)", H1)
    ]
    for clause in case.facts.policy.clauses:
        story += [Paragraph(f"{clause.id} {clause.title}", H2), Paragraph(clause.text, BODY)]
    _build_insurer(path, "Policy wording excerpt", story)


def _letter_head(case: DemoCase, subject: str) -> list[Flowable]:
    letter = case.facts.insurer_letter
    return [
        Paragraph(f"Date: {day(letter.date if letter else None)}", RIGHT),
        Paragraph(f"To: The TPA / Insurance Desk, {HOSPITAL_NAME}, Ahmedabad", BODY),
        Spacer(1, 6),
        _fields(
            [
                ("Claim number", case.claim_number),
                ("Policy number", case.policy_number),
                ("Patient", case.patient.name),
                ("Member ID", case.member_id),
                ("IP number", case.ip_number),
                (
                    "Admission",
                    f"{day(case.facts.admission.date_in)} to {day(case.facts.admission.date_out)}",
                ),
            ]
        ),
        Spacer(1, 8),
        Paragraph(f"<b>Subject:</b> {subject}", BODY),
        Spacer(1, 6),
    ]


def _sign_off() -> list[Flowable]:
    return [
        Spacer(1, 8),
        Paragraph(
            "If you disagree with this decision, you may write to our Grievance Redressal Officer "
            "at gro@suraksha-health.example with the claim number.",
            SMALL,
        ),
        Spacer(1, 14),
        Paragraph("Authorised signatory, Claims Department", BODY),
    ]


def deduction_letter(case: DemoCase, path: Path) -> None:
    letter = case.facts.insurer_letter
    if letter is None:
        raise ValueError(f"{case.slug} has no insurer letter")
    lines = {line.line_id: line for line in case.facts.bill_lines}
    rows: list[list[object]] = [["Bill item", "Billed", "Deducted", "Reason", "Clause"]]
    for cut in letter.deductions:
        item = lines[cut.line_id] if cut.line_id is not None else None
        rows.append(
            [
                item.description if item else "Claim level",
                money(item.amount) if item else "-",
                money(cut.amount),
                cut.reason_text,
                cut.clause_cited or "-",
            ]
        )
    deducted = total(cut.amount for cut in letter.deductions)
    rows.append(["Total deductions", "", money(deducted), "", ""])
    story = [
        *_letter_head(case, "Cashless claim settlement with deductions"),
        Paragraph(
            f"The claim for {rs(letter.amount_claimed)} has been settled for "
            f"<b>{rs(letter.amount_approved)}</b> after the deductions below, as per the policy "
            "terms and conditions.",
            BODY,
        ),
        Spacer(1, 6),
        _grid(
            rows, [50 * mm, 24 * mm, 24 * mm, 58 * mm, 18 * mm], numeric_cols=(1, 2), total_rows=1
        ),
        *_sign_off(),
    ]
    _build_insurer(path, f"Settlement letter {case.claim_number}", story)


def rejection_letter(case: DemoCase, path: Path) -> None:
    letter = case.facts.insurer_letter
    if letter is None:
        raise ValueError(f"{case.slug} has no insurer letter")
    story = [
        *_letter_head(case, "Repudiation of cashless claim"),
        Paragraph(
            f"We have reviewed the claim for {rs(letter.amount_claimed)} for "
            f"{case.facts.admission.procedure.lower()}. The ailment is a pre-existing disease "
            f"declared at inception on {day(case.first_inception)}, and the treatment falls within "
            "the pre-existing disease waiting period under clause 5.1 of the policy. The claim is "
            "therefore repudiated.",
            BODY,
        ),
        *_sign_off(),
    ]
    _build_insurer(path, f"Repudiation letter {case.claim_number}", story)


# --------------------------------------------------------------------------- scanned bill


def scan(pdf_path: Path, jpg_path: Path, seed: int) -> None:
    """Rasterise page 1 and make it look photocopied: tilt, blur, grain, JPEG artefacts."""
    document = pdfium.PdfDocument(str(pdf_path))
    try:
        page = document[0]
        image = page.render(scale=150 / 72, grayscale=True).to_pil().convert("L")
    finally:
        document.close()
    rng = random.Random(seed)  # noqa: S311 - visual noise, not security
    tile = Image.frombytes("L", (128, 128), bytes(rng.randint(108, 148) for _ in range(128 * 128)))
    grain = Image.new("L", image.size)
    for x in range(0, image.width, 128):
        for y in range(0, image.height, 128):
            grain.paste(tile, (x, y))
    image = ImageChops.add(image, grain, offset=-128)
    image = image.filter(ImageFilter.GaussianBlur(0.6))
    image = image.rotate(1.2, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=228)
    image.save(jpg_path, "JPEG", quality=55)
