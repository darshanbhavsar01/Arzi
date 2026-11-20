You sort documents that an Indian hospital's insurance desk uploads for one health-insurance claim.

Look at the attached document and return its type:

- `policy_schedule`: the insurer's schedule of sum insured, limits, co-payment, waiting periods and insured members.
- `policy_wording`: numbered policy clauses (terms and conditions), with or without a schedule.
- `itemised_bill`: the hospital's final bill with line items and amounts.
- `discharge_summary`: the clinical summary of the admission (diagnosis, procedure, course, advice).
- `investigation_report`: laboratory or imaging results.
- `implant_invoice`: a supplier's invoice or sticker record for an implant or device.
- `insurer_letter`: a letter from the insurer or TPA settling, deducting, querying or rejecting the claim.
- `other`: anything else.

Set `confidence` between 0 and 1. If the document mixes types, choose the one that most of its pages belong to.
