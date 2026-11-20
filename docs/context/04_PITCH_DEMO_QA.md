# Pitch, demo and judge Q&A

## 1. Three-minute pitch skeleton
1. **Hook (15s):** "It's 6 pm on discharge day. The family is at the counter. The insurer has just cut ₹68,000 from their bill, and nobody can say why." (Use the demo case number.)
2. **Problem (30s):** ₹29,933 Cr was rejected or deducted in FY25. Most of it comes from mechanical rules nobody checks before filing. 41% of Ombudsman health cases go in the policyholder's favour, yet most families never appeal.
3. **Solution (20s):** Arzi audits every claim **before** submission and drafts **clause-cited** appeals **after** a cut, then explains it to the family in Gujarati, Hindi or English.
4. **Live demo (75s):** see below
5. **Business (20s):** hospitals pay ₹15–40k a month or per claim; families use it free and pay a 10–15% success fee only on recovered money; we start with 5–10 Gujarat hospitals. **Traction:** `[quotes / LOI from Day 1 calls]`
6. **Google AI (15s):** Gemini reads the documents and reasons over them, Gemini Live speaks to families, Gemma keeps patient data inside the hospital's cloud, ADK orchestrates the agents, and it all runs serverless on Cloud Run in Mumbai.
7. **Why me (10s):** 5 years building document-intelligence and agentic systems on Google Cloud for enterprises, with a hospital advisor `[name]`.
8. **Close:** "Arzi: your claim, defended before and after the insurer says no."

## 2. Demo script (75 seconds)
1. Upload the case A bill, policy and discharge summary → "Patient identifiers redacted" badge appears
2. Extraction appears (bill lines categorised) → **₹67,887 at risk**, 4 flags, each with a clause citation
3. Click the room-rent flag → fix: "Move to an eligible room or take upgrade consent. Saves ₹46,875."
4. Switch to case C (rejection letter) → **appeal draft** citing the 36-month PED rule → "Reviewed and signed by" step
5. Press 🔊 → Gemini Live explains the claim in **Gujarati** to the family

Always have a **recorded backup video** and cached JSON ready.

## 3. Judging criteria → proof points
| Criterion | What to show |
|---|---|
| Founder profile | Enterprise doc-AI and ADK experience, GDG ADK speaker, a domain advisor, a personal story |
| Product potential | A working end-to-end demo; three jobs on one claim record; free tool as a distribution loop |
| Market viability | 40k cashless hospitals, 3.26 Cr claims a year, a named buyer and price, a Gujarat pilot plan, **real quotes or an LOI** |
| Technical architecture | Deterministic ₹ engine plus LLM reasoning, grounded citations, per-hospital isolation, serverless scaling, cost per claim tracked, evals |
| Use of Google AI | Gemini multimodal, Gemini Live, Gemma, ADK/Agent Engine, Document AI, Vertex AI Search, BigQuery. **Live versus roadmap must be stated honestly.** |

## 4. Likely judge questions and answers
- **"Why won't insurers or TPAs just do this themselves?"** Their incentive is to pay less. Hospitals and families need an independent auditor. HMIS modules are generic and don't read policy wording.
- **"Isn't this a ChatGPT wrapper?"** No. The rupee maths is a deterministic rules engine. The LLM extracts and cites from a whitelist, and every output traces to a clause. The workflow runs before submission, inside the desk's process.
- **"What about hallucinated citations?"** Agents can only cite clause and rule IDs present in context; there's schema validation, an evaluation set, and a human signs every appeal.
- **"Data privacy?"** DPDP-aligned: redaction before reasoning (Gemma inside the hospital's project), Mumbai region, consent and audit log, VPC-SC isolation per hospital.
- **"Liability if an appeal fails?"** It's decision support; the hospital or family files. The success fee is charged only on recovery.
- **"Why will hospitals pay?"** Every deduction becomes a patient dispute or a write-off and slows discharge. A free retrospective audit shows the recoverable ₹ first.
- **"How do you get the first 10 customers?"** Founder-led in Ahmedabad, Surat and Rajkot, through hospital billing networks and the advisor; the free family tool creates inbound demand.
- **"Unit economics?"** Mostly Gemini Flash; cost per claim is tracked in Cloud Monitoring `[fill in measured ₹/claim]` against a ₹100 audit fee.
- **"How accurate is it?"** `[fill in eval result on demo set, e.g., X/Y deductions caught]`
- **"What's next?"** NHCX/FHIR integration, more insurers' policy wordings, an insurer-level deduction analytics product, then the GCC markets.
