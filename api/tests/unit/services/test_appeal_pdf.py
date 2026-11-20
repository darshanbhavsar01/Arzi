import pypdfium2 as pdfium

from arzi.services.appeal import citation_label, identity_fields
from arzi.services.appeal_pdf import Letter, LetterItem, render_letter

DIGEST = "ab" * 32


def _letter(argument: str = "The cut is contrary to the cited rules.", items: int = 1) -> Letter:
    return Letter(
        hospital_name="Sanjeevani Multispeciality Hospital",
        hospital_city="Ahmedabad",
        addressee=["The Grievance Redressal Officer", "Suraksha Health Insurance Co. (fictional)"],
        date="20 November 2026",
        references=[("Patient", "Test Patient"), ("Hospital reference", "ARZ-1, appeal version 1")],
        subject="Request to review <deductions> & co-pay",
        facts="Admitted on 2026-03-14.",
        items=[
            LetterItem(
                title="Proportionate deduction",
                lines=["Pharmacy and medicines"],
                amount="₹19,237.50",
                insurer_reason="Proportionate deduction applied",
                argument=argument,
                citations=["Policy clause 4.3"],
            )
        ]
        * items,
        relief="We request that the insurer pay ₹20,137.50.",
        enclosures=["Copy of the insurer's letter"],
        reviewer_name="R. Mehta",
        reviewer_role="TPA desk manager",
        signed_on="20 November 2026",
        content_sha256=DIGEST,
    )


def _pages(data: bytes) -> list[str]:
    document = pdfium.PdfDocument(data)
    try:
        return [" ".join(page.get_textpage().get_text_range().split()) for page in document]
    finally:
        document.close()


def test_the_letter_is_reproducible_and_escapes_markup() -> None:
    first, second = render_letter(_letter()), render_letter(_letter())
    assert first == second
    (page,) = _pages(first)
    assert "Subject: Request to review <deductions> & co-pay" in page
    assert f"Content SHA-256: {DIGEST}" in page
    assert "Page 1 of 1" in page
    assert "₹19,237.50" in page


def test_every_page_carries_the_footer_and_the_page_count() -> None:
    long = " ".join(["The deduction is contrary to the circular and the policy."] * 30)
    pages = _pages(render_letter(_letter(long, items=4)))
    assert len(pages) >= 2
    for number, page in enumerate(pages, start=1):
        assert f"Page {number} of {len(pages)}" in page
        assert f"Content SHA-256: {DIGEST}" in page
        assert "Prepared with Arzi decision support; reviewed and signed by R. Mehta." in page


def test_citation_labels() -> None:
    assert citation_label("policy:4.3") == "Policy clause 4.3"
    verified = citation_label("IRDAI_PROP_DED_2020")
    assert verified == (
        "Norms on proportionate deductions (IRDAI/HLT/REG/CIR/151/06/2020, 11 June 2020)"
    )
    # A reference still marked "verify" prints its title only, never the internal note.
    assert (
        citation_label("IRDAI_NON_PAYABLE_ANNEX_I")
        == "Non-payable items: Annexure I, Lists I to IV"
    )


def test_identity_fields_come_from_the_vault_by_kind() -> None:
    vault = {
        "P-7F3A": "Test Patient",
        "[POLICY_NUMBER-1A2B]": "POL/1",
        "[PHONE-9C9C]": "+91 99999 00000",
    }
    assert identity_fields(vault, "P-7F3A") == [
        ("Patient", "Test Patient"),
        ("Policy number", "POL/1"),
    ]
    assert identity_fields({}, "P-7F3A") == []
