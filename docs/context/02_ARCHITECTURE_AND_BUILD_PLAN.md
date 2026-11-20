# Arzi: architecture and two-day build plan

## 1. Target architecture (as pitched in the deck)

Four layers: **Capture → Protect → Reason → Deliver**.

```
1 CAPTURE                2 PROTECT                 3 REASON (ADK on Vertex AI Agent Engine)        4 DELIVER
-----------------        -----------------         -------------------------------------------     ---------------------------
Web app (TPA desk)  ─┐   Gemma on Cloud Run   ─┐   Extractor        (Gemini + Document AI OCR)  ┌─ Cloud Run API + web dashboard
Family upload        ├─► Sensitive Data        ├─► Policy Interpreter (Gemini + Vertex AI Search) ├─ Firestore claim records
 (web / WhatsApp)    │   Protection: redact    │   Bill Auditor     (Rules engine + Gemini)       ├─ Gemini Live voice for families
Bills, policies,     │   patient identifiers   │   Appeal Drafter   (Gemini, grounded + cited)    ├─ BigQuery + Looker Studio analytics
 discharge notes,    │   Consent + audit log   │   Voice Explainer  (Gemini Live)                 └─ (Nano Banana one-page explainer)
 insurer letters  ───┘   (DPDP)                │   Rules engine (Cloud Run): exact ₹ maths
Cloud Storage (Mumbai) + Pub/Sub ──────────────┘
```

**Security and operations:** Identity Platform, IAM and VPC Service Controls isolate each hospital. Cloud Logging, Trace and Vertex AI evaluation track accuracy and **cost per claim**. Terraform handles repeatable onboarding. Everything is serverless, so it scales per claim with near-zero idle cost. **Next:** claims arrive through NHCX (FHIR) APIs.

**Model roles**
- **Gemini** (via the Gemini API on Vertex AI) reads scanned bills, handwritten discharge summaries, policy PDFs and rejection letters into structured JSON. It maps bill lines to clauses and IRDAI rules, grounded in retrieved text, drafts appeals, and powers the ADK agents.
- **Gemini Live** gives real-time voice explanations to families in Gujarati, Hindi and English.
- **Gemma** runs on Cloud Run inside the hospital's own GCP project. It redacts and classifies documents before the main pipeline, so sensitive data stays under the hospital's control.
- Supporting services: Vertex AI (serving and evaluation), Agent Engine plus ADK (runtime), Document AI (OCR for poor scans), Vertex AI Search (grounding on policy wordings and circulars).

**Build flow pitched:** prototype in **AI Studio** → build in **Antigravity** → package checks as **Agent Skills** → deploy on **Google Cloud**.

---

## 2. What to actually build in two days (solo)

The rule: one end-to-end workflow that works on stage beats five half-working modules. Make the load-bearing Google pieces **real**, and present the rest as the **roadmap** on the architecture slide.

### Must have (demo breaks without these)
1. **Upload** of the policy, itemised bill, discharge summary and/or insurer letter (PDF or image) to GCS
2. **Extractor:** Gemini multimodal turns the documents into the `Claim` JSON below, using structured output with a response schema
3. **Rules engine** (pure Python, deterministic) for the top 5 checks: proportionate room rent, non-payables, sub-limits, co-pay, waiting period/PED
4. **Flags** with ₹ at risk, a **citation** (policy clause text or IRDAI rule ID) and a **fix suggestion**
5. **Appeal Drafter:** Gemini writes a letter citing only the provided rules and clauses. A "Reviewed and signed by" field is required before export.
6. **Dashboard:** one claim page showing total billed, ₹ at risk, a flags table, the appeal draft and a download
7. **Deployed on Cloud Run** in `asia-south1`, with Firestore for claims

### Should have (big for judging criterion 5)
8. **Voice Explainer** with Gemini Live, explaining the claim in Gujarati or Hindi. A pre-generated audio fallback is fine.
9. **ADK orchestration:** Extractor → Policy Interpreter → Bill Auditor (calls the rules engine as a tool) → Appeal Drafter. Run locally with `adk web` if Agent Engine deploy is slow.
10. A **regex/SDP redaction step** (names, phone numbers, Aadhaar-like and policy-number patterns) before Gemini, shown in the UI as "Patient identifiers redacted"

### Could have (only if ahead of schedule)
11. Gemma redaction service on Cloud Run · 12. Vertex AI Search datastore over policy PDFs and the IRDAI list · 13. BigQuery export plus one Looker Studio chart of deductions by insurer · 14. Nano Banana illustrated "why your claim was cut" card · 15. Agent Skills packaging of the checks

---

## 3. Data model: `Claim` (Firestore doc, Gemini response schema)

```json
{
  "claim_id": "ARZ-2026-0001",
  "mode": "pre_submission | post_deduction | post_rejection",
  "hospital": {"name": "", "city": "", "room_categories": [{"name": "", "rate_per_day": 0}]},
  "patient": {"redacted_id": "P-xxxx", "age": 0},
  "policy": {
    "insurer": "", "product": "", "policy_start": "YYYY-MM-DD", "continuous_cover_months": 0,
    "sum_insured": 0, "room_rent_cap": {"type": "per_day_amount | pct_of_si | category", "value": 0},
    "icu_cap_per_day": null, "copay_pct": 0, "deductible": 0,
    "sub_limits": [{"item": "cataract", "limit": 0, "clause": ""}],
    "ped_declared": [{"condition": "", "waiting_months": 36}],
    "specific_waiting": [{"condition": "", "waiting_months": 24}],
    "non_payable_cover_addon": false,
    "clauses": [{"id": "4.2", "title": "", "text": ""}]
  },
  "admission": {"date_in": "", "date_out": "", "diagnosis": "", "procedure": "", "icd10": "", "room_category_used": "", "days_room": 0, "days_icu": 0},
  "bill_lines": [
    {"line_id": 1, "description": "", "category": "room | icu | surgeon | anaesthetist | ot | nursing | consultation | pharmacy | consumable | implant | diagnostics | non_payable | other",
     "amount": 0, "qty": 1, "source_page": 1}
  ],
  "insurer_letter": {"type": "deduction | rejection | query", "date": "", "amount_claimed": 0, "amount_approved": 0,
                     "reasons": [{"text": "", "amount": 0, "clause_cited": ""}]},
  "flags": [
    {"rule_id": "PROP_ROOM_RENT", "severity": "high", "amount_at_risk": 0, "lines": [1,2],
     "explanation": "", "citation": {"source": "policy | irdai", "ref": "", "quote": ""},
     "fix": "", "appealable": true}
  ],
  "totals": {"billed": 0, "predicted_payable": 0, "at_risk": 0, "recoverable_on_appeal": 0},
  "appeal": {"forum": "insurer_gro | bima_bharosa | ombudsman", "draft_md": "", "reviewed_by": null, "signed_at": null},
  "audit_log": [{"ts": "", "actor": "", "action": ""}],
  "consent": {"given_by": "", "ts": "", "purpose": "claim_audit"}
}
```

---

## 4. Rules engine (deterministic, `rules/engine.py`)

Each rule takes the `Claim` and returns `Flag[]`. **Amounts come only from here.**

| rule_id | Logic | Citation (see file 03) |
|---|---|---|
| `PROP_ROOM_RENT` | If room rate used > cap: `ratio = cap / actual`. Room excess = `(actual − cap) × days`. Proportionate cut applies **only to "associated medical expenses"** (surgeon, anaesthetist, OT, nursing, consultation, as the policy defines them). **Never** to pharmacy and consumables, implants and devices, diagnostics, or **ICU charges**. | IRDAI/HLT/REG/CIR/151/06/2020 (proportionate deduction norms) plus the policy clause |
| `PROP_WRONGLY_APPLIED` | *(post-deduction)* The insurer letter applied the ratio to pharmacy, diagnostics, implants or ICU, so the full amount is recoverable | Same circular, paras 4 and 7 |
| `NON_PAYABLE` | Match bill lines against the IRDAI List I (not payable unless an add-on covers it). For List II, III and IV items, flag **"should be subsumed into room, procedure or treatment cost, so not a separate deduction"**. If the policy has a non-payable add-on, don't deduct. | IRDAI Annexure I, Lists I–IV |
| `SUB_LIMIT` | If the procedure has a sub-limit, cut the excess above the limit | Policy clause |
| `COPAY` | `copay_pct × admissible amount` (age or zone co-pay per policy) | Policy clause |
| `WAITING_PERIOD` | If the condition is PED or has a specific waiting period and `continuous_cover_months < waiting_months`, there's a rejection risk. If cover ≥ 36 months for PED, or ≥ 60 months (moratorium, no fraud), **a rejection on non-disclosure or PED grounds is appealable**. | IRDAI 2024 PED max 36 months; moratorium 60 months |
| `DOC_MISSING` | Required documents missing (discharge summary, investigation reports, implant sticker/invoice) | Policy claims clause |

**Worked example (use it as a unit test and demo case A).** Room cap ₹5,000/day; ward used ₹8,000/day × 4 days; ICU 1 day ₹15,000; surgeon ₹60,000; OT ₹25,000; nursing ₹8,000; pharmacy ₹30,000; diagnostics ₹12,000; implant ₹40,000; non-payables ₹3,500; co-pay 10%.
- ratio = 0.625 · Room payable ₹20,000 (excess **₹12,000**)
- Associated (surgeon + OT + nursing = ₹93,000) × 0.625 = ₹58,125 (cut **₹34,875**)
- ICU, pharmacy, diagnostics and implant are paid in full (no proportionate cut) · Non-payable cut **₹3,500**
- Admissible ₹1,75,125 → co-pay **₹17,512.50** → **payable ₹1,57,612.50** of ₹2,25,500 billed
- **Total at risk ₹67,887.50.** Fix: *"Move the patient to an eligible ₹5,000 room, or get a written upgrade consent. Doing so saves ₹46,875."*
- (Co-pay base differs by policy. Read it from the policy clause.)

---

## 5. Agents (Google ADK)

```
root: ArziOrchestrator (LlmAgent, Gemini Flash)
 ├─ ExtractorAgent      tools: gcs_read, docai_ocr(optional) → Claim JSON (response_schema)
 ├─ PolicyInterpreter   tools: search_policy_clauses (Vertex AI Search or in-memory clause list) → maps limits/caps to clause ids
 ├─ BillAuditor         tools: run_rules_engine(claim) → flags (LLM only writes explanations + fix text)
 ├─ AppealDrafter       tools: get_flags, get_clause_text → appeal_md (cite only provided refs; forum-specific format)
 └─ VoiceExplainer      Gemini Live session, system prompt in gu/hi/en, reads flags summary
```
Guardrails: give each agent a citation whitelist (only clause and rule IDs in context); a Pydantic schema check after every step; a `confidence` field on extraction; low-confidence lines are shown for human confirmation.

**Appeal letter format** (insurer GRO, Bima Bharosa or Ombudsman): addressee and forum → policy and claim numbers → facts (admission dates, amounts claimed and approved) → **each disputed deduction**: amount, the insurer's reason, why it's wrong, and the citation → relief sought (₹ total) → enclosures list → "Reviewed and signed by" plus date. Add the ₹50 lakh limit and the 1-year deadline note for the Ombudsman.

---

## 6. Repo layout

```
arzi/
  app/                 # FastAPI (Cloud Run): /upload /claims/{id} /audit /appeal /voice-token
    main.py  models.py (Pydantic Claim)  storage.py (GCS, Firestore)
  agents/              # ADK agents + tools
    orchestrator.py extractor.py policy.py auditor.py appeal.py voice.py
  rules/
    engine.py  rules_*.py  data/irdai_non_payable.json  data/rule_citations.json
    tests/test_worked_example.py
  web/                 # simple UI (HTML/Tailwind or Streamlit/Mesop for speed), Arzi colours
  demo_cases/          # case_a/, case_b/, case_c/ (synthetic PDFs + expected.json)
  evals/               # extraction + flag accuracy on demo cases
  infra/               # deploy.sh (gcloud run deploy ... --region asia-south1), terraform/ (stretch)
```

Quick-start commands (verify flags at the event):
```bash
gcloud config set project <PROJECT_ID>; gcloud config set run/region asia-south1
gcloud services enable run.googleapis.com aiplatform.googleapis.com firestore.googleapis.com storage.googleapis.com documentai.googleapis.com
gcloud firestore databases create --location=asia-south1
gcloud storage buckets create gs://<PROJECT_ID>-arzi-uploads --location=asia-south1
pip install google-adk google-genai fastapi uvicorn pydantic google-cloud-firestore google-cloud-storage
gcloud run deploy arzi-api --source . --region asia-south1 --allow-unauthenticated
```

---

## 7. Demo cases (synthetic, prepared before the build)
- **Case A, pre-submission audit:** the worked example above. The desk sees ₹67,887 at risk and a fix that saves ₹46,875 *before* filing.
- **Case B, deduction appeal:** the insurer letter applied the 0.625 ratio to pharmacy, diagnostics and ICU and deducted List II/IV items separately. Arzi flags `PROP_WRONGLY_APPLIED` plus subsumed items and drafts a GRO appeal for the recoverable ₹.
- **Case C, rejection appeal:** a knee replacement was rejected for "PED waiting period". The policy has 40 months of continuous cover with PED declared, against a 36-month maximum waiting period, so the rejection is invalid. Arzi drafts a clause-cited appeal and a Gujarati voice explanation for the family.

---

## 8. Hour-by-hour plan

**Day 1 (20 Nov): ideate, design and get the skeleton working**
- Kick-off: note the rules, submission format and judging rubric details, and ask mentors what "traction" means here
- H1–2: GCP project, APIs, bucket, Firestore, a hello-world on Cloud Run
- H2–4: Extractor prompt and schema tuned in **AI Studio** on cases A, B and C
- H4–6: rules engine plus tests (the worked example must pass)
- Mentor rounds: pressure-test pricing and the buyer; **call hospital desks for quotes**
- Evening: wire upload → extract → rules → flags into the API; start ADK wiring

**Day 2 (21 Nov): build, polish, submit and pitch**
- H1–3: Appeal Drafter plus dashboard UI (Arzi brand)
- H3–4: Gemini Live voice explainer (Gujarati/Hindi), with a recorded fallback
- H4–5: deploy, run the end-to-end demo 3 times, **record a backup screen video**
- H5: update the deck (traction slide, live architecture, demo screenshots); **submit before the deadline**
- Pitch, then Q&A (see file 04)

**Fallbacks:** if Agent Engine deploy stalls, run ADK in the Cloud Run container. If Gemini Live fails on venue Wi-Fi, play the pre-recorded audio. If extraction is flaky, use cached JSON for the demo case and show live extraction on one page.
