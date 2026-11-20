"""The committed demo cases are exactly what the generator and the engine produce today."""

import hashlib
import json
import re
from pathlib import Path

import pypdfium2 as pdfium
import pytest
from demo_data import CASES, DemoCase, aadhaar_like, verhoeff_valid
from demo_documents import in_words, money
from gen_demo_cases import expected, generate_case
from PIL import Image, ImageChops, ImageStat

from arzi.domain.models import ClaimFacts
from arzi.domain.money import Paise, rupees, total
from arzi.rules.engine import audit
from tests.unit.rules.helpers import DEMO_CASES

CASE_IDS = [case.slug for case in CASES]


@pytest.fixture(scope="module")
def regenerated(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("demo_cases")
    for case in CASES:
        generate_case(case, out)
    return out


def _pdf_text(path: Path) -> str:
    document = pdfium.PdfDocument(str(path))
    try:
        text = " ".join(page.get_textpage().get_text_range() for page in document)
    finally:
        document.close()
    return re.sub(r"\s+", " ", text)


def _case_text(case: DemoCase) -> str:
    return " ".join(_pdf_text(p) for p in sorted((DEMO_CASES / case.slug).glob("*.pdf")))


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_engine_on_facts_equals_expected(case: DemoCase) -> None:
    directory = DEMO_CASES / case.slug
    facts = ClaimFacts.model_validate_json((directory / "facts.json").read_bytes())
    committed = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    assert expected(audit(facts)) == committed


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_committed_facts_match_the_case_definition(case: DemoCase) -> None:
    committed = (DEMO_CASES / case.slug / "facts.json").read_bytes()
    assert ClaimFacts.model_validate_json(committed) == case.facts


# Its sha256 follows the platform's JPEG encoder; compared field by field below instead.
SCAN_FIXTURE = Path("case_a") / "extraction" / "bill_scanned.jpg.json"


def _generated(root: Path) -> list[Path]:
    return sorted(
        p.relative_to(root)
        for p in root.rglob("*")
        if p.suffix in {".pdf", ".json"}
        and "llm_cache" not in p.parts
        and (p.parent.name.startswith("case_") or p.parent.name == "extraction")
    )


def test_regeneration_is_byte_identical(regenerated: Path) -> None:
    committed = _generated(DEMO_CASES)
    assert committed == _generated(regenerated)
    changed = [
        str(rel)
        for rel in committed
        if rel != SCAN_FIXTURE
        and (DEMO_CASES / rel).read_bytes() != (regenerated / rel).read_bytes()
    ]
    assert not changed, f"run `make demo-cases` and commit: {changed}"


def test_scan_fixture_matches_apart_from_the_image_hash(regenerated: Path) -> None:
    old = json.loads((DEMO_CASES / SCAN_FIXTURE).read_text(encoding="utf-8"))
    new = json.loads((regenerated / SCAN_FIXTURE).read_text(encoding="utf-8"))
    assert {**old, "sha256": None} == {**new, "sha256": None}
    scan = (DEMO_CASES / "case_a" / "bill_scanned.jpg").read_bytes()
    assert old["sha256"] == hashlib.sha256(scan).hexdigest()


def test_scanned_bill_matches_within_codec_tolerance(regenerated: Path) -> None:
    """JPEG and rasteriser builds can differ by a few levels across platforms; layout cannot."""
    rel = Path("case_a") / "bill_scanned.jpg"
    with Image.open(DEMO_CASES / rel) as old, Image.open(regenerated / rel) as new:
        assert old.size == new.size
        assert ImageStat.Stat(ImageChops.difference(old, new)).mean[0] < 1.0
    assert not (DEMO_CASES / "case_b" / "bill_scanned.jpg").exists()


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_identifiers_are_on_the_documents_and_never_in_facts(case: DemoCase) -> None:
    text = _case_text(case)
    facts = (DEMO_CASES / case.slug / "facts.json").read_text(encoding="utf-8")
    identifiers = json.loads((DEMO_CASES / case.slug / "identifiers.json").read_text("utf-8"))
    assert identifiers == case.identifiers()
    for kind, value in identifiers.items():
        assert value in text, f"{kind} not printed on any {case.slug} document"
        assert value not in facts, f"{kind} leaked into facts.json"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_aadhaar_like_numbers_fail_the_checksum(case: DemoCase) -> None:
    number = case.patient.aadhaar_like
    assert re.fullmatch(r"[2-9]\d{3} \d{4} \d{4}", number)
    assert not verhoeff_valid(number)


def test_verhoeff_reference_values() -> None:
    assert verhoeff_valid("2363")  # the textbook example: 236 has check digit 3
    assert not verhoeff_valid("2364")
    assert not verhoeff_valid(aadhaar_like("23630000000"))


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_bill_prints_every_line_and_the_total(case: DemoCase) -> None:
    text = _pdf_text(DEMO_CASES / case.slug / "itemised_bill.pdf")
    for line in case.facts.bill_lines:
        assert f"{line.description}" in text
        assert money(line.amount) in text
    grand = total(line.amount for line in case.facts.bill_lines)
    assert money(grand) in text
    assert in_words(grand) in text


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_every_page_says_it_is_synthetic(case: DemoCase) -> None:
    for pdf in (DEMO_CASES / case.slug).glob("*.pdf"):
        document = pdfium.PdfDocument(str(pdf))
        try:
            for page in document:
                assert "Synthetic test document" in page.get_textpage().get_text_range(), pdf.name
        finally:
            document.close()


def test_insurer_letters_carry_the_letter_amounts() -> None:
    b_text = _pdf_text(DEMO_CASES / "case_b" / "insurer_deduction_letter.pdf")
    assert "Rs. 1,38,375.00" in b_text
    assert "88,125.00" in b_text  # claimed 2,26,500 - approved 1,38,375
    c_text = _pdf_text(DEMO_CASES / "case_c" / "insurer_rejection_letter.pdf")
    assert "repudiated" in c_text
    assert "clause 5.1" in c_text


@pytest.mark.parametrize(
    ("amount", "words"),
    [
        (rupees(225_500), "Rupees Two Lakh Twenty-Five Thousand Five Hundred Only"),
        (
            Paise(15_761_250),
            "Rupees One Lakh Fifty-Seven Thousand Six Hundred Twelve and Fifty Paise Only",
        ),
        (rupees(31_000_000), "Rupees Three Crore Ten Lakh Only"),
        (rupees(0), "Rupees Zero Only"),
        (Paise(5), "Rupees Zero and Five Paise Only"),
    ],
)
def test_amount_in_words_uses_indian_numbering(amount: Paise, words: str) -> None:
    assert in_words(amount) == words


@pytest.mark.parametrize(
    ("case", "printed"),
    [
        ("case_a", "10% of admissible claim"),
        ("case_b", "10% of admissible claim"),
        ("case_c", "1% of sum insured per day"),
    ],
)
def test_percentages_print_as_plain_numbers(case: str, printed: str) -> None:
    """Regression: Decimal(10).normalize() renders as '1E+1' unless formatted with 'f'."""
    text = _pdf_text(DEMO_CASES / case / "policy_schedule.pdf")
    assert printed in text
    assert "E+" not in text
