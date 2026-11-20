# Source of the IRDAI non-payable lists

- **File:** `IRDAI_Modification_Guidelines_Standardization_Health_Insurance_2019.pdf`
- **Document:** IRDAI, "Modification Guidelines on Standardization in Health Insurance",
  dated 27 September 2019. Annexure I sets out List I (optional items), List II (subsumed into
  room charges), List III (subsumed into procedure charges) and List IV (subsumed into costs of
  treatment).
- **Circular number:** IRDAI/HLT/REG/CIR/___/09/2019. The number is unreadable in the scan's text
  layer, and the IRDAI web page text suggests 176. Confirm it against the printed page before
  citing it.
- **Downloaded:** 2026-11-20 from irdai.gov.in, document page `document-detail?documentId=392476`
  (file link "Modification Guidelines on Standardization in Health Insurance.pdf").
- **SHA-256:** `ca53bb9d872e89c854359d4ea72e8a676ccc36dd05f401100490264485ae3e1a`

## Notes

- The PDF is a scan with an OCR text layer. A parser must correct OCR slips (for example
  "List Ill" for List III, "FLEX! MASK", "LUM BO SACRAL BELT"), and a person reviews the result
  before any item is marked verified.
- The domain brief says these lists were carried into the Master Circular on Health Insurance
  Business (IRDAI/HLT/CIR/PRO/84/5/2024, 29 May 2024). Check whether that circular changed any
  item before flipping statuses.

## How it is loaded

`scripts/parse_non_payable.py` reads this PDF and writes
`api/src/arzi/rules/data/irdai_non_payable.json` and `PARSED_LISTS.md` (the review sheet). It
refuses to write if the item numbering breaks or a list size differs from the printed annexure
(I: 68, II: 37, III: 23, IV: 18), and a test fails if either output is out of date. Every item stays
at status `verify` until the review below is done.

## Review before marking items verified

1. Check `PARSED_LISTS.md` against the scanned pages, item by item.
2. Confirm the circular number on the printed first page.
3. Check the 2024 Master Circular's annexure for any changed items.
4. Then set `status` to `verified` in the parser and regenerate.
