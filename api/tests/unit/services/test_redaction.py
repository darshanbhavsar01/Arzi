import json

import pytest
from pydantic import BaseModel

from arzi.domain.enums import LineCategory
from arzi.services.extraction_schemas import (
    BillExtraction,
    BillLineText,
    DischargeExtraction,
    InsurerLetterExtraction,
    LetterKind,
    PersonIdentifiers,
    PolicyExtraction,
)
from arzi.services.redaction import Redactor
from tests.unit.rules.helpers import DEMO_CASES

REDACTOR = Redactor(b"test-key")
SCHEMAS: dict[str, type[BaseModel]] = {
    "policy_schedule.pdf": PolicyExtraction,
    "policy_wording_excerpt.pdf": PolicyExtraction,
    "itemised_bill.pdf": BillExtraction,
    "discharge_summary.pdf": DischargeExtraction,
    "insurer_deduction_letter.pdf": InsurerLetterExtraction,
    "insurer_rejection_letter.pdf": InsurerLetterExtraction,
}


@pytest.mark.parametrize("case", ["case_a", "case_b", "case_c"])
def test_every_demo_identifier_is_removed(case: str) -> None:
    documents = []
    for name, schema in SCHEMAS.items():
        path = DEMO_CASES / case / "extraction" / f"{name}.json"
        if path.exists():
            documents.append(
                schema.model_validate(json.loads(path.read_text("utf-8"))["extraction"])
            )
    outcome = REDACTOR.redact(documents)

    text = " ".join(doc.model_dump_json() for doc in outcome.documents).lower()
    identifiers = json.loads((DEMO_CASES / case / "identifiers.json").read_text("utf-8"))
    for kind, value in identifiers.items():
        assert value.lower() not in text, kind
        assert value in outcome.vault.values(), kind
    assert outcome.patient_pseudonym == REDACTOR.pseudonym("name", identifiers["patient_name"])
    assert outcome.summary.total >= len(identifiers)


def test_name_parts_in_free_text_map_to_the_same_pseudonym() -> None:
    letter = InsurerLetterExtraction(
        identifiers=PersonIdentifiers(patient_name="Ramesh Kantilal Parmar"),
        kind=LetterKind.REJECTION,
        rejection_reason="Mr. PARMAR was treated for a pre-existing condition.",
    )
    outcome = REDACTOR.redact([letter])
    reason = outcome.documents[0].rejection_reason or ""
    alias = REDACTOR.pseudonym("name", "Ramesh Kantilal Parmar")
    assert reason == f"Mr. {alias} was treated for a pre-existing condition."
    assert outcome.vault[alias] == "Ramesh Kantilal Parmar"


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Call +91 98765 43210 for the report", "phone"),
        ("Mobile 9876543210", "phone"),
        ("Aadhaar 7351 9284 0610 on file", "aadhaar"),  # Verhoeff-invalid: still removed
        ("UID 234567890123", "aadhaar"),
        ("PAN ABCPE1234F", "pan"),
        ("Write to family.member@example.com", "email"),
    ],
)
def test_patterns_catch_identifiers_the_extractor_missed(text: str, kind: str) -> None:
    bill = BillExtraction(
        lines=[
            BillLineText(
                serial=1,
                description=text,
                category=LineCategory.OTHER,
                qty="1",
                amount="10",
                page=1,
                confidence=1,
            )
        ]
    )
    outcome = REDACTOR.redact([bill])
    assert outcome.summary.counts == {kind: 1}
    assert outcome.documents[0].lines[0].description != text


@pytest.mark.parametrize(
    "text",
    ["Rs. 2,25,500.00", "Total 1,57,612.50", "IP/2026/10/0731 dated 2026-10-12", "ICD-10 S72.0"],
)
def test_amounts_dates_and_codes_are_left_alone(text: str) -> None:
    bill = BillExtraction(printed_total=text)
    assert REDACTOR.redact([bill]).documents[0].printed_total == text


def test_pseudonyms_are_stable_and_keyed() -> None:
    assert REDACTOR.pseudonym("name", "Hemlata  Joshi") == REDACTOR.pseudonym(
        "name", "hemlata joshi"
    )
    assert REDACTOR.pseudonym("name", "Hemlata Joshi").startswith("P-")
    assert REDACTOR.pseudonym("phone", "x").startswith("[PHONE-")
    assert Redactor(b"other-key").pseudonym("name", "Hemlata Joshi") != REDACTOR.pseudonym(
        "name", "Hemlata Joshi"
    )


def test_nothing_to_redact() -> None:
    outcome = REDACTOR.redact([BillExtraction(printed_total="Rs. 100")])
    assert outcome.summary.total == 0
    assert outcome.patient_pseudonym is None
