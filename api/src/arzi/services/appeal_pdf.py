"""The signed appeal as a PDF: hospital letterhead, letter body, disputed-items table, signature.

Rendered with reportlab in invariant mode, so the same signed version always produces the same
bytes. IBM Plex fonts (SIL Open Font License, in ``arzi/assets/fonts``) are embedded and carry
the ₹ sign. Every page's footer prints the content SHA-256 and "Prepared with Arzi decision
support; reviewed and signed by <name>". Pure: the caller supplies everything to print.
"""

import io
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import cache
from importlib.resources import as_file, files
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

NAVY = colors.HexColor("#1E2A44")
ACCENT = colors.HexColor("#D9482B")
SLATE = colors.HexColor("#CDD3E0")
MUTED = colors.HexColor("#5A6478")
_FONTS = {
    "Plex": "IBMPlexSans-Regular.ttf",
    "Plex-SemiBold": "IBMPlexSans-SemiBold.ttf",
    "PlexMono": "IBMPlexMono-Regular.ttf",
}
_MARGIN = 20 * mm


@dataclass(frozen=True)
class LetterItem:
    title: str
    lines: Sequence[str]
    """The bill lines the item covers."""
    amount: str
    insurer_reason: str
    argument: str
    citations: Sequence[str]


@dataclass(frozen=True)
class Letter:
    hospital_name: str
    hospital_city: str
    addressee: Sequence[str]
    date: str
    references: Sequence[tuple[str, str]]
    """(label, value) pairs: patient, policy number, claim number, version."""
    subject: str
    facts: str
    items: Sequence[LetterItem]
    relief: str
    enclosures: Sequence[str]
    reviewer_name: str
    reviewer_role: str
    signed_on: str
    content_sha256: str


@cache
def _register_fonts() -> None:
    root = files("arzi").joinpath("assets", "fonts")
    for name, filename in _FONTS.items():
        with as_file(root.joinpath(filename)) as path:
            pdfmetrics.registerFont(TTFont(name, str(path)))


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("body", fontName="Plex", fontSize=10, leading=14.5, textColor=NAVY)
    return {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=8.5, leading=12, textColor=MUTED),
        "strong": ParagraphStyle("strong", parent=base, fontName="Plex-SemiBold"),
        "hospital": ParagraphStyle(
            "hospital", parent=base, fontName="Plex-SemiBold", fontSize=16, leading=20
        ),
        "heading": ParagraphStyle(
            "heading", parent=base, fontName="Plex-SemiBold", fontSize=11, spaceBefore=6
        ),
        "cell": ParagraphStyle("cell", parent=base, fontSize=8.5, leading=11.5),
        "amount": ParagraphStyle(
            "amount", parent=base, fontName="Plex-SemiBold", fontSize=8.5, leading=11.5, alignment=2
        ),
    }


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(text).replace("\n", "<br/>"), style)


class _Rule(Flowable):
    def __init__(self, width: float, colour: colors.Color, thickness: float) -> None:
        super().__init__()
        self.width, self.colour, self.thickness = width, colour, thickness

    def wrap(self, *_: float) -> tuple[float, float]:
        return self.width, self.thickness + 2

    def draw(self) -> None:
        self.canv.setStrokeColor(self.colour)
        self.canv.setLineWidth(self.thickness)
        self.canv.line(0, 1, self.width, 1)


def _footer(letter: Letter, total: int | None) -> Callable[[Canvas, Any], None]:
    """Each page's footer: the reviewer line, the content hash and "Page n of m"."""

    def draw(canvas: Canvas, _doc: Any) -> None:  # noqa: ANN401 - reportlab doc template
        width, _ = A4
        canvas.saveState()
        canvas.setStrokeColor(SLATE)
        canvas.setLineWidth(0.5)
        canvas.line(_MARGIN, 18 * mm, width - _MARGIN, 18 * mm)
        canvas.setFillColor(MUTED)
        canvas.setFont("Plex", 7.5)
        canvas.drawString(
            _MARGIN,
            14 * mm,
            f"Prepared with Arzi decision support; reviewed and signed by {letter.reviewer_name}.",
        )
        page = canvas.getPageNumber()
        canvas.drawRightString(width - _MARGIN, 14 * mm, f"Page {page} of {total or page}")
        canvas.setFont("PlexMono", 6.5)
        canvas.drawString(_MARGIN, 10.5 * mm, f"Content SHA-256: {letter.content_sha256}")
        canvas.restoreState()

    return draw


def _items_table(letter: Letter, s: dict[str, ParagraphStyle], width: float) -> Table:
    header = [_p(h, s["strong"]) for h in ("Item", "Amount", "Insurer's reason", "Our grounds")]
    rows: list[list[Any]] = [header]
    for item in letter.items:
        grounds = escape(item.argument)
        if item.citations:
            refs = "; ".join(escape(c) for c in item.citations)
            grounds += f'<br/><font color="#5A6478" size="7.5">References: {refs}</font>'
        title = f'<font name="Plex-SemiBold">{escape(item.title)}</font>'
        if item.lines:
            title += f'<br/><font color="#5A6478" size="7.5">{escape("; ".join(item.lines))}</font>'
        rows.append(
            [
                Paragraph(title, s["cell"]),
                _p(item.amount, s["amount"]),
                _p(item.insurer_reason, s["cell"]),
                Paragraph(grounds, s["cell"]),
            ]
        )
    table = Table(
        rows, colWidths=[w * width for w in (0.21, 0.16, 0.19, 0.44)], repeatRows=1, hAlign="LEFT"
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.8, NAVY),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, SLATE),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def _story(letter: Letter) -> list[Flowable]:
    s = _styles()
    width = A4[0] - 2 * _MARGIN
    story: list[Flowable] = [
        _p(letter.hospital_name, s["hospital"]),
        _p(letter.hospital_city, s["small"]),
        Spacer(0, 2 * mm),
        _Rule(width, ACCENT, 1.6),
        Spacer(0, 6 * mm),
        _p(letter.date, s["body"]),
        Spacer(0, 4 * mm),
        *(_p(line, s["body"]) for line in letter.addressee),
        Spacer(0, 4 * mm),
    ]
    references = Table(
        [[_p(label, s["small"]), _p(value, s["body"])] for label, value in letter.references],
        colWidths=[0.24 * width, 0.76 * width],
        hAlign="LEFT",
    )
    references.setStyle(
        TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)])
    )
    story += [
        references,
        Spacer(0, 4 * mm),
        _p(f"Subject: {letter.subject}", s["strong"]),
        Spacer(0, 3 * mm),
        _p(letter.facts, s["body"]),
        Spacer(0, 2 * mm),
        _p("Items in dispute", s["heading"]),
        _items_table(letter, s, width),
        Spacer(0, 3 * mm),
        _p(letter.relief, s["body"]),
    ]
    if letter.enclosures:
        story += [_p("Enclosures", s["heading"])]
        story += [_p(f"{i}. {e}", s["body"]) for i, e in enumerate(letter.enclosures, start=1)]
    story += [
        Spacer(0, 8 * mm),
        _p("Reviewed and signed by", s["small"]),
        _p(letter.reviewer_name, s["strong"]),
        _p(f"{letter.reviewer_role}, {letter.hospital_name}", s["body"]),
        _p(f"Signed on {letter.signed_on}", s["small"]),
    ]
    return story


def render_letter(letter: Letter) -> bytes:
    _register_fonts()
    # Two passes: the first counts the pages so every footer can say "Page n of m".
    total: int | None = None
    for _ in range(2):
        out = io.BytesIO()
        doc = SimpleDocTemplate(
            out,
            pagesize=A4,
            leftMargin=_MARGIN,
            rightMargin=_MARGIN,
            topMargin=18 * mm,
            bottomMargin=26 * mm,
            title=f"Appeal: {letter.subject}",
            author=letter.hospital_name,
            creator="Arzi",
            invariant=1,
        )
        footer = _footer(letter, total)
        doc.build(_story(letter), onFirstPage=footer, onLaterPages=footer)
        total = doc.page
    return out.getvalue()
