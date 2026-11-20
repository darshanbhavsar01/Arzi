# Demo cases

Three synthetic claims that exercise the whole product offline: extraction from PDFs and a
scanned image, redaction, the rules engine, appeals and the family explanation. They are the
fixtures for tests and evals, and the three journeys shown live.

Everything here is fictional. "Sanjeevani Multispeciality Hospital" and "Suraksha Health
Insurance Co. (fictional)" do not exist, and every page carries a footer saying the document is a
synthetic test document. Do not edit these files by hand: change `scripts/demo_data.py` and run
`make demo-cases`. A test fails if the committed files differ from a fresh generation.

## Files in each case

| File | What it is |
|---|---|
| `facts.json` | Engine input (`ClaimFacts`): what extraction should produce after redaction and human confirmation. Amounts are integer paise. |
| `expected.json` | Engine output for `facts.json`: flags, totals, citations with their verified/verify status. Reviewed by hand against `docs/BUILD_PLAN.md`. |
| `identifiers.json` | Every synthetic personal identifier printed on the documents. Redaction must remove all of them, and none appears in `facts.json`. |
| `policy_schedule.pdf`, `policy_wording_excerpt.pdf` | Policy limits, waiting periods and the numbered clauses (4.2 room rent, 4.3 proportionate deduction, 5.1 PED, 7.4 co-payment, 8.1 non-medical expenses, 9.2 claim documents). |
| `itemised_bill.pdf` | Final in-patient bill: patient block, line items with qty and rate, totals by service head, amount in words. |
| `discharge_summary.pdf`, `investigation_reports.pdf`, `implant_invoice.pdf` | The supporting documents an insurer asks for. |
| `insurer_deduction_letter.pdf` (B), `insurer_rejection_letter.pdf` (C) | The insurer's decision. |
| `bill_scanned.jpg` (A) | The bill as a tilted, grainy photocopy, to prove extraction works on images. |

## The cases

**A: pre-submission audit (Ramesh Kantilal Parmar, 67).** Hip hemiarthroplasty after a fall. He
stayed in an ₹8,000/day room against a ₹5,000/day cap, with 10% co-pay and three List I items on
the bill. Before the claim goes out, the desk sees **₹67,887.50 at risk** across four flags:
room-rent excess ₹12,000, proportionate deduction ₹34,875, non-payables ₹3,500 and co-pay
₹17,512.50. ICU, pharmacy, diagnostics and the implant are untouched. **Moving him to an eligible
room, or taking written upgrade consent, avoids ₹46,875.**

**B: deduction appeal (Hemlata Dilip Joshi, 54).** The same bill plus ₹1,000 registration
charges, already settled. The insurer approved ₹1,38,375. It prorated pharmacy (₹11,250),
diagnostics (₹4,500) and ICU (₹5,625), which the 2020 proportionate-deduction circular does not
allow, and it deducted registration charges, which are part of treatment cost, as a separate
item. The correct payable is ₹1,58,512.50, so **₹20,137.50 is recoverable** (₹19,237.50 + ₹900,
net of co-pay). Arzi drafts the Grievance Redressal Officer appeal for a human to sign. The ₹900
item cites a list whose item text is still marked "Verify before filing".

**C: rejection appeal (Bhanuben Mahendra Patel, 63).** Right total knee replacement, rejected
for the pre-existing disease waiting period. Osteoarthritis of the knee was declared at
inception on 20-Jun-2023, which gives **40 months of continuous cover** against a waiting period
capped at 36 months. The rejection does not hold. The relief sought is the full admissible
₹3,10,000, and the family hears the explanation in Gujarati.

## Synthetic identifiers

- Names come from a fixed list of common Gujarati names; addresses are fictional societies.
- Phone numbers follow Arzi's test pattern `+91 99999 0XXXX`. This is not an officially reserved
  range, only a pattern that redaction tests look for.
- Aadhaar-like numbers have 12 digits and a deliberately wrong Verhoeff check digit, so none is a
  valid Aadhaar number. PAN-like values start with `ZQX`.
- Emails use the reserved `example.com` domain.

## Determinism

reportlab runs in invariant mode with the Vera fonts bundled in reportlab embedded, and page
streams are left uncompressed (zlib builds differ across platforms), so the PDFs regenerate byte
for byte. The test suite checks that on every run, locally and on Linux in CI. The scan uses a
fixed noise seed. JPEG and rasteriser builds can differ by a few grey levels across platforms,
so the test compares the scan within a small pixel tolerance.
