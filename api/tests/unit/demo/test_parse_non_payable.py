"""The engine's IRDAI list is exactly what the parser reads from the official PDF."""

import pytest
from parse_non_payable import OUT, PDF, REVIEW, aliases, entries, main, page_texts, parse, render


def test_committed_json_matches_the_official_pdf() -> None:
    assert OUT.read_text(encoding="utf-8") == render(entries(parse(page_texts(PDF))))
    assert REVIEW.exists()
    assert main(["--check"]) == 0


def test_broken_numbering_is_refused() -> None:
    pages = page_texts(PDF)
    damaged = [pages[0], pages[1].replace("6 COLD PACK/HOT PACK", "COLD PACK/HOT PACK"), *pages[2:]]
    with pytest.raises(ValueError, match="list sizes"):
        parse(damaged)


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("LAUNDRY CHARGES", ["laundry charges", "laundry"]),
        (
            "ADMISSION/REGISTRATION CHARGES",
            [
                "admission registration charges",
                "admission charges",
                "registration charges",
                "registration",
            ],
        ),
        ("COLD PACK/HOT PACK", ["cold pack hot pack", "cold pack", "hot pack"]),
        ("DIAPER OF ANY TYPE", ["diaper of any type", "diaper"]),
        ("EYE SHEILD", ["eye sheild", "eye shield"]),
        # Conditions cannot be checked by a matcher, so only the full wording is kept.
        (
            "OXYGEN CYLINDER (FOR USAGE OUTSIDE THE HOSPITAL)",
            ["oxygen cylinder for usage outside the hospital"],
        ),
        (
            "SERVICE CHARGES WHERE NURSING CHARGE ALSO CHARGED",
            ["service charges where nursing charge also charged"],
        ),
    ],
)
def test_alias_generation(item: str, expected: list[str]) -> None:
    assert aliases(item) == expected
