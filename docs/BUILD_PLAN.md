# Arzi — Build Plan (phased execution)

> Companion to `AGENTS.md` (rules) and `docs/PROGRESS.md` (status). Context documents from the
> founder live in `docs/context/` (master brief, architecture, IRDAI domain rules, pitch/demo,
> submitted deck text). When this plan and a context doc disagree on **engineering**, this plan
> wins; on **regulation**, `docs/context/03_DOMAIN_RULES_IRDAI.md` wins.
>
> **How to use:** "Read AGENTS.md and docs/BUILD_PLAN.md. Execute Phase N only. Stop at the
> Phase N gate and report." Each phase lists goal, tasks, specs, the acceptance gate and a
> suggested commit sequence.

---

## Product in one paragraph

The billing executive at a 150-bed private hospital uploads the policy, the discharge summary
and the itemised bill. Arzi extracts everything with Gemini, redacts patient identifiers,
runs a deterministic IRDAI + policy rules engine, and shows every likely deduction with the
₹ at risk, the exact clause or IRDAI rule, and the fix before filing. After an insurer cuts or
rejects a claim, Arzi drafts a clause-cited appeal that a human reviews and signs, and explains
the outcome to the family in Gujarati, Hindi or English, including by voice.

**Three demo journeys must work flawlessly (synthetic data):**
- **A — Pre-submission audit:** ₹67,887.50 at risk, 4 flags, fix saves ₹46,875.
- **B — Deduction appeal:** insurer prorated pharmacy/diagnostics/ICU and deducted a subsumed
  item → ₹20,137.50 recoverable → GRO appeal draft → sign → PDF.
- **C — Rejection appeal:** knee replacement rejected for PED waiting; 40 months continuous
  cover vs 36-month maximum → rejection invalid → appeal + Gujarati voice explanation.

---

## Phase map and schedule

| Phase | Name | Priority | Est. | When |
|---|---|---|---|---|
| 0 | Bootstrap, guardrails, GCP + billing | Must | 1 h | Day 1, **first** (before 11:50 IST) |
| 1 | Domain model + deterministic rules engine | Must | 2.5 h | Day 1 |
| 2 | Synthetic demo cases + fixtures | Must | 1 h | Day 1 |
| 3 | Ingestion, Gemini extraction, redaction, persistence, live pipeline (SSE), cost ledger | Must | 3 h | Day 1 evening |
| 4 | ADK agents: policy interpreter, flag explainer, appeal drafter, guardrails, sign + PDF | Must | 2.5 h | Day 2 morning |
| 5 | Desk web app (enterprise UI) | Must | 4 h | Day 2 (start shell on Day 1 if ahead) |
| 6 | Family experience: multilingual explainer, voice, share link, free "check my rejection" | Should | 2.5 h | Day 2 |
| 7 | Production hardening: auth, tenancy, security, observability, evals | Should | 2 h | Day 2 |
| 8 | Analytics + insights | Could | 1 h | Day 2 if ahead |
| 9 | Release, rehearsal, docs, submission | Must | 1.5 h | Day 2, before deadline |

**Cut line if behind at Day 2 noon:** finish 4 → 5 (worklist, workspace, appeal editor only) →
6 (pre-generated audio, no live Q&A) → 9. Skip 8 and the claim copilot. Auth falls back to
demo sign-in. Never cut tests on the rules engine or the guardrails.

---

## Phase 0 — Bootstrap, guardrails, GCP + billing

**Goal:** a clean monorepo with quality tooling and attribution guardrails, a GCP project in
`asia-south1` with budgets, and a hello-world deployed to Cloud Run.

### 0.1 Repository scaffold
1. Create the layout in `AGENTS.md §3`. `api/` uses `uv` with a `src/` layout; `web/` uses
   Vite React-TS.
2. `Makefile` with every target in `AGENTS.md §9` (stubs allowed for later phases, but they
   must exit cleanly with a "not yet implemented (Phase N)" message).
3. Python tooling in `api/pyproject.toml`: ruff (rules: E,F,I,B,UP,SIM,RUF,ASYNC,S,PT,N,ANN),
   mypy strict, pytest with `--strict-markers`, coverage `fail_under = 85`, a separate
   coverage gate of 100% for `src/arzi/rules` (run as a second pytest-cov invocation in
   `make check`).
4. Web tooling: TypeScript `strict`, `noUncheckedIndexedAccess`; ESLint flat config with
   typescript-eslint strict + react-hooks + jsx-a11y; Prettier; Vitest; Playwright.
5. `.githooks/commit-msg` (POSIX sh) rejects messages containing any `Co-Authored-By:` line,
   any line starting `Generated with`, or the robot emoji. Print a helpful error.
   `make setup` runs `git config core.hooksPath .githooks`.
6. `.github/workflows/ci.yml`: jobs `api` (uv sync, ruff, mypy, pytest), `web` (npm ci, lint,
   tsc, vitest, build), `commits` (fails if any commit in the PR has a `Co-Authored-By:` trailer).
   No cloud secrets in CI. Cache uv and npm.
7. `.editorconfig`, `.gitignore` (Python, Node, `.env*`, `dist/`, `coverage/`, `.venv/`,
   `playwright-report/`, `demo_cases/**/out/`). No tool-specific entries.
8. `docs/PROGRESS.md` from the template at the end of this file; `docs/adr/0001-record-architecture-decisions.md`.
9. `README.md` skeleton: one-line pitch, screenshot placeholder, quick start (`make setup && make dev`), architecture link, "Live vs roadmap" link, licence placeholder.
10. Copy `arzi-logo.png` to `web/public/brand/`.

### 0.2 GCP bootstrap — `infra/bootstrap.sh` (idempotent, `set -euo pipefail`)
Variables at top: `PROJECT_ID`, `REGION=asia-south1`, `BILLING_ACCOUNT_EVENT`,
`BILLING_ACCOUNT_OWNER`, `BUCKET=${PROJECT_ID}-arzi-docs`, `SA=arzi-run`.

```bash
gcloud billing accounts list                                   # find both account IDs
gcloud projects create "$PROJECT_ID" --name="Arzi"             # skip if exists
gcloud config set project "$PROJECT_ID"
gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_EVENT"
gcloud config set run/region "$REGION"

gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com aiplatform.googleapis.com firestore.googleapis.com \
  storage.googleapis.com secretmanager.googleapis.com logging.googleapis.com \
  cloudtrace.googleapis.com iamcredentials.googleapis.com identitytoolkit.googleapis.com \
  firebase.googleapis.com texttospeech.googleapis.com billingbudgets.googleapis.com
# optional, only when Phase 7 enables them: documentai.googleapis.com dlp.googleapis.com

gcloud firestore databases create --location="$REGION" --type=firestore-native
gcloud storage buckets create "gs://$BUCKET" --location="$REGION" \
  --uniform-bucket-level-access --public-access-prevention
gcloud storage buckets update "gs://$BUCKET" --lifecycle-file=infra/gcs-lifecycle.json  # delete after 30 days

gcloud iam service-accounts create "$SA" --display-name="Arzi Cloud Run runtime"
# least privilege (infra/iam.sh): roles/aiplatform.user, roles/datastore.user,
# roles/logging.logWriter, roles/cloudtrace.agent, roles/secretmanager.secretAccessor (project);
# roles/storage.objectAdmin (bucket only); roles/iam.serviceAccountTokenCreator on itself (signed URLs)
```
- Firestore security rules `infra/firestore.rules`: **deny all client access** (backend uses
  the Admin SDK only). Deploy with the Firebase CLI.
- Add Firebase to the project (`firebase projects:addfirebase "$PROJECT_ID"`) and enable the
  Email/Password and Google sign-in providers.
- Artifact Registry cleanup policy (keep the 3 newest images) on the `cloud-run-source-deploy`
  repo once it exists after the first deploy: `infra/ar-cleanup.json`.

### 0.3 Billing safety — `infra/budgets.sh`
- Budget on **each** billing account, filtered to this project, thresholds 25/50/90/100%.
  The currency must match the account's currency:
  ```bash
  gcloud billing budgets create --billing-account="$BILLING_ACCOUNT_OWNER" \
    --display-name="arzi-cap" --budget-amount=500INR \
    --filter-projects="projects/$PROJECT_ID" \
    --threshold-rule=percent=0.25 --threshold-rule=percent=0.5 \
    --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
  ```
- **Switchover (owner action, before 11:50 IST on 20 Nov; confirm the exact expiry under
  Billing → Credits):**
  ```bash
  gcloud billing projects link "$PROJECT_ID" --billing-account="$BILLING_ACCOUNT_OWNER"
  gcloud billing projects describe "$PROJECT_ID"   # verify billingEnabled: true and the new account
  ```
  Write this as `make billing-switch` with a confirmation prompt. The agent never runs it
  without the owner saying so.
- **Budgets alert; they do not cap spend.** The spend kill switches are:
  `gcloud run services update arzi --update-env-vars ARZI_LLM_MODE=replay` (stops all model
  spend instantly) and `--max-instances=1`. Document both in `docs/runbook.md`.

### 0.4 Hello world + model discovery
- `GET /healthz` (liveness) and `GET /readyz` (checks Firestore + GCS reachability) in FastAPI.
- `scripts/list_models.py` lists the Gemini models visible via `google-genai` on Vertex AI
  (`client.models.list()`), filtered to gemini/gemma/tts/live. `make models` prints them.
  Choose the newest Flash, Pro, TTS and Live-capable models, check that each is served in
  `asia-south1` (otherwise use `global`), and record the choice + date in `docs/PROGRESS.md`.
- First deploy: `infra/deploy.sh` → `gcloud run deploy arzi --source . --region asia-south1
  --service-account arzi-run@… --min-instances 0 --max-instances 3 --cpu 1 --memory 1Gi
  --concurrency 20 --timeout 300 --allow-unauthenticated --set-env-vars …`. (App-level auth
  comes in Phase 7; the API rejects unauthenticated calls except `/healthz`, `/family/*`
  and `/check`.)

**Gate:** `make setup && make check` green on an empty-but-wired codebase · commit-msg hook
rejects a test message containing a co-author trailer · `/healthz` returns 200 from the Cloud
Run URL · budgets visible · model choice recorded.

**Commits:** `chore: scaffold monorepo` → `chore(ci): add lint/test workflow` →
`chore(git): add commit-msg guard` → `chore(infra): add gcp bootstrap and budgets` →
`feat(api): add health endpoints` → `chore(infra): first cloud run deploy`.

---

## Phase 1 — Domain model + deterministic rules engine

**Goal:** the heart of the product. Pure, typed, 100%-tested Python that turns claim facts into
flags and totals with a human-readable computation trace. No I/O, no LLM.

### 1.1 Domain (`arzi/domain/`)
- `money.py`: `Paise` NewType; `to_paise(value: str | int | Decimal) -> Paise` (handles
  "₹1,57,612.50", "Rs. 8000/-", "8,000.00"); `ratio_apply(amount, num, den) -> Paise` using
  `Decimal` and `ROUND_HALF_UP`; `format_inr(p: Paise) -> str` (en-IN grouping) for tests/docs.
- `enums.py`: `ClaimMode` (pre_submission, post_deduction, post_rejection), `LineCategory`
  (room, icu, surgeon, anaesthetist, ot, nursing, consultation, pharmacy, consumable, implant,
  diagnostics, non_payable, other), `Severity`, `CitationStatus` (verified, verify),
  `AppealForum` (insurer_gro, bima_bharosa, ombudsman), `ClaimStatus`.
- `state.py`: explicit claim state machine
  `draft → documents_uploaded → processing → audited → appeal_drafted → in_review → signed → exported`,
  plus `failed` (retryable back to `documents_uploaded`). `transition(current, event)` raises on
  illegal moves. Tested exhaustively.
- `models.py` (Pydantic v2). Evolves `docs/context/02` §3 with these changes:
  - all money fields are `Paise` (int); every bill line has `line_id`, `description`,
    `category`, `amount`, `qty`, `source_page`, `confidence`, `irdai_list` (`I|II|III|IV|None`),
    `confirmed_by_human: bool`;
  - `policy` gains `room_rent_cap {type: per_day_amount|pct_of_si|category, value, clause_id}`,
    `icu_cap_per_day`, `copay {pct, base: admissible|claimed, clause_id}`,
    `associated_expense_categories` (default: surgeon, anaesthetist, ot, nursing, consultation),
    `continuous_cover_months`, `ped_declared[]`, `specific_waiting[]`, `sub_limits[]`,
    `non_payable_addon`, `clauses[] {id, title, text, page}`;
  - `Flag {flag_id, rule_id, severity, amount_at_risk, recoverable, lines[], citation_refs[],
    fix_code, fix_savings, appealable, trace_ref}` — narrative text is added later by the
    explainer agent in a separate `FlagNarrative`;
  - `Totals {billed, predicted_payable, at_risk, recoverable_on_appeal}`;
  - `ComputationTrace[] {step_id, rule_id, formula, inputs, result}` e.g.
    `"₹93,000 × 5,000 / 8,000 = ₹58,125"`;
  - `ClaimFacts` (input to engine) is separate from `ClaimRecord` (persisted: facts + flags +
    totals + runs + appeals + audit refs + `hospital_id`, `status`, `schema_version`).

### 1.2 Rules (`arzi/rules/`)
`engine.audit(facts: ClaimFacts) -> AuditResult(flags, totals, trace)`. Each rule is a pure
function `(facts, ctx) -> list[Flag]` registered in an ordered registry. Order matters:
non-payables → sub-limits → room/ICU caps + proportionate → co-pay → waiting periods → documents.

| rule_id | Logic | Citation refs |
|---|---|---|
| `ROOM_RENT_EXCESS` | Effective cap per day from cap type (`pct_of_si` → % × SI; `category` → hospital's rate for that category). If room rate > cap: excess = (rate − cap) × days. | policy room-rent clause |
| `PROP_ROOM_RENT` | Same trigger. ratio = cap/rate; cut on associated-expense categories only = amount × (1 − ratio). **Never** prorate pharmacy, consumables, implants, diagnostics or ICU. Fix (shared with `ROOM_RENT_EXCESS`): move to an eligible room or take written upgrade consent; `fix_savings` = room excess + proportionate cut. | `IRDAI_PROP_DED_2020`, policy proportionate clause |
| `ICU_CAP` | If ICU rate > `icu_cap_per_day`, cut the excess only (no proportionate). | policy ICU clause |
| `NON_PAYABLE` | Lines matched to IRDAI List I (and not covered by an add-on) are cut. | `IRDAI_NON_PAYABLE_ANNEX_I` |
| `SUBSUMED_ITEM` | Lines matching Lists II–IV: pre-submission → warn "bill as part of room/procedure/treatment", no cut; post-deduction → if the insurer cut it separately, recoverable. | `IRDAI_NON_PAYABLE_ANNEX_I` (status verify) |
| `SUB_LIMIT` | Procedure sub-limit exceeded → cut excess. | policy clause |
| `COPAY` | `pct × base` where base comes from the policy (default admissible). | policy clause |
| `WAITING_PERIOD` | Pre-submission: PED/specific condition with cover < waiting → high-risk flag (no ₹ cut computed; whole claim at risk shown separately). | policy clause, `IRDAI_PED_36M` |
| `WAITING_REJECTION_INVALID` | Post-rejection on PED/waiting grounds where effective waiting = min(policy waiting, 36) ≤ continuous cover → appealable. | `IRDAI_PED_36M` |
| `MORATORIUM` | Post-rejection on non-disclosure with cover ≥ 60 months and no fraud alleged → appealable. | `IRDAI_MORATORIUM_60M` |
| `PROP_WRONGLY_APPLIED` | Post-deduction: insurer reason lines show the ratio applied to excluded categories → recoverable = amount cut on those lines. | `IRDAI_PROP_DED_2020` |
| `DOC_MISSING` | Required docs per mode/procedure missing (discharge summary, investigation reports, implant invoice/sticker when an implant line exists). | policy claims clause |

Post-deduction mode compares engine-correct payable with `insurer_letter` amounts line by
line; `recoverable_on_appeal` is net of co-pay.

### 1.3 Reference data (`arzi/rules/data/`)
- `rule_citations.json` — `{id, title, source_doc, ref, summary_en, status, url?}`. Seed from
  `docs/context/03` **exactly**, preserving its status marks:
  `IRDAI_MC_2024` (IRDAI/HLT/CIR/PRO/84/5/2024, 29 May 2024 — verified),
  `IRDAI_CASHLESS_TAT` (1 h pre-auth / 3 h discharge — **verify** para),
  `IRDAI_PROP_DED_2020` (IRDAI/HLT/REG/CIR/151/06/2020 — verified; any paragraph number → verify),
  `IRDAI_PED_36M` (verified), `IRDAI_MORATORIUM_60M` (verified),
  `IRDAI_NON_PAYABLE_ANNEX_I` (structure verified; item list **verify** until loaded from the
  official PDF), `INSURER_GRIEVANCE_15D` (**verify**), `OMBUDSMAN_RULES_2017` (verified: 1 month
  wait, 1 year limit, ₹50 lakh cap, free), `BIMA_BHAROSA` (verified).
  A unit test asserts every `rule_id` in the registry has ≥ 1 citation and every citation's
  status is set.
- `irdai_non_payable.json` — `{list: I|II|III|IV, item, aliases[], source, status}`. Seed only
  with items named in `docs/context/03` (e.g., baby food, beauty services, laundry,
  cold/hot pack, crepe bandage; admission/registration charges under List IV) with
  `status: verify`. If the owner places the official Annexure PDF in `docs/context/irdai/`,
  write `scripts/parse_non_payable.py` to load the full list and flip `status` to verified.
  Never type items from memory.
- Matcher `rules/matching.py`: normalise (lowercase, strip punctuation/qty/units), exact alias
  match first, then `rapidfuzz` token-set ratio ≥ 90; returns match + score; below threshold
  → `None` (the LLM's category suggestion is shown as a hint for human confirmation, never
  auto-applied as a cut).

### 1.4 Tests (`api/tests/unit/rules/`)
- **Golden test — case A** (from `docs/context/02` §4): cap ₹5,000/day; ward ₹8,000 × 4;
  ICU 1 × ₹15,000; surgeon ₹60,000; OT ₹25,000; nursing ₹8,000; pharmacy ₹30,000;
  diagnostics ₹12,000; implant ₹40,000; List I items ₹3,500; co-pay 10% on admissible.
  Expect: billed **₹2,25,500**; room excess **₹12,000**; proportionate cut **₹34,875**;
  non-payable **₹3,500**; admissible **₹1,75,125**; co-pay **₹17,512.50**; payable
  **₹1,57,612.50**; at risk **₹67,887.50**; fix savings **₹46,875**; exactly 4 flags:
  `ROOM_RENT_EXCESS` ₹12,000 · `PROP_ROOM_RENT` ₹34,875 · `NON_PAYABLE` ₹3,500 ·
  `COPAY` ₹17,512.50 (the ICU, pharmacy, diagnostics and implant lines carry no flag).
- **Golden — case B:** case A bill + "Registration charges ₹1,000" (List IV). Insurer letter
  prorated pharmacy (₹11,250), diagnostics (₹4,500) and ICU (₹5,625) and cut registration
  (₹1,000) separately. Correct payable = (₹1,75,125 + ₹1,000) × 0.9 = **₹1,58,512.50**;
  insurer approved **₹1,38,375.00**; recoverable = (₹21,375 + ₹1,000) × 0.9 = **₹20,137.50**
  (the ₹900 subsumed-item portion carries a `verify` citation).
- **Golden — case C:** PED (knee osteoarthritis) declared, policy PED waiting 36 months,
  continuous cover 40 months, rejection reason "PED waiting period" → `WAITING_REJECTION_INVALID`,
  appealable, relief = admissible amount per the engine for the claimed bill.
- Edge cases: no cap; cap equals rate; `pct_of_si`; `category` cap; ICU cap; add-on covers
  non-payables; co-pay on claimed base; multiple sub-limits; zero-amount lines; rounding at
  ₹0.005 boundaries; cover exactly 36 / 60 months.
- Hypothesis properties listed in `AGENTS.md §8`.

**Gate:** 100% line+branch coverage on `arzi/rules`, mypy strict clean, the three golden tests
pass, `python -m arzi.rules.cli demo_cases/case_a/facts.json` prints the flag table and trace.

**Commits:** `feat(domain): add money and claim models` → `feat(domain): add claim state machine`
→ `feat(rules): add proportionate room rent rule` → … one per rule → `feat(rules): add citation
registry` → `test(rules): add golden cases and properties`.

---

## Phase 2 — Synthetic demo cases + fixtures

**Goal:** realistic, clearly fictional documents that exercise extraction, plus expected
outputs, so every later phase can be tested offline.

1. `scripts/gen_demo_cases.py` (reportlab + Pillow) writes per case to `demo_cases/case_x/`:
   - `policy_schedule.pdf` (fictional "Suraksha Health Insurance Co. (fictional)", product,
     SI, room-rent cap, ICU cap, co-pay, sub-limits, PED declared, policy start date) and
     `policy_wording_excerpt.pdf` with numbered clauses (e.g., 4.2 Room rent, 4.3
     Proportionate deduction, 5.1 PED waiting, 7.4 Co-payment, 9.2 Claim documents);
   - `itemised_bill.pdf` (fictional "Sanjeevani Multispeciality Hospital, Ahmedabad",
     realistic Indian bill layout: header, UHID (synthetic), IP number, admission/discharge,
     category subtotals, line items, GST lines where realistic, grand total);
   - `discharge_summary.pdf` (diagnosis, ICD-10, procedure, room category, stay dates);
   - case B: `insurer_deduction_letter.pdf` with a deduction table and reasons; case C:
     `insurer_rejection_letter.pdf`;
   - `bill_scanned.jpg` for case A: the bill rendered as an image with slight rotation, noise
     and JPEG artefacts to prove multimodal robustness.
   - All personal data synthetic (names from a fixed fictional list, fake phone numbers in a
     reserved pattern, a 12-digit Aadhaar-*like* test number that fails Verhoeff) — so the
     redaction step has something to redact.
2. `facts.json` (engine input) and `expected.json` (flags, totals, citations) per case, generated
   from the Phase 1 engine and **hand-checked** against the numbers above.
3. `demo_cases/README.md` describing each case and the story for the pitch.

**Gate:** `make demo-cases` regenerates byte-stable PDFs (fixed seeds, fixed fonts) · PDFs open
and look like real documents · engine on each `facts.json` equals `expected.json`.

**Commits:** `feat(demo): add synthetic document generator` → `test(demo): add expected outputs`.

---

## Phase 3 — Ingestion, extraction, redaction, persistence, live pipeline

**Goal:** upload documents → live, streamed audit → persisted claim record. Real Gemini calls
in `live` mode, recorded responses in `replay` mode.

### 3.1 Adapters
- `adapters/genai_client.py` — `LlmClient` protocol + Vertex implementation using
  `google-genai` (`genai.Client(vertexai=True, project, location)`). Methods:
  `generate_structured(model, parts, schema, prompt_ref) -> (model_obj, Usage)` and
  `generate_text(...)`. Files go in as `Part.from_uri(file_uri="gs://…", mime_type=…)`.
  `response_mime_type="application/json"`, `response_schema=<Pydantic model>`, low
  temperature, `max_output_tokens`, configurable thinking budget (check the parameter for the
  chosen model). Timeout and retry policy per `AGENTS.md §4`. Record/replay wrapper keyed by
  `sha256(prompt_ref + inputs)` storing JSON under `demo_cases/*/llm_cache/`.
- `adapters/gcs.py` — upload with content-type sniffing (`python-magic` or header check),
  V4 signed URLs for viewing (10 min), path `hospitals/{hid}/claims/{cid}/{doc_id}.{ext}`.
- `adapters/firestore_repo.py` — `ClaimRepository` (async client). Collections:
  ```
  hospitals/{hid}                                  profile, room_categories
  hospitals/{hid}/claims/{cid}                     ClaimRecord (keep < 1 MB)
  hospitals/{hid}/claims/{cid}/documents/{did}     metadata, gcs_uri, doc_type, pages, sha256
  hospitals/{hid}/claims/{cid}/runs/{rid}          stages, timings, models, prompt versions, tokens, cost
  hospitals/{hid}/claims/{cid}/events/{eid}        append-only audit log
  hospitals/{hid}/claims/{cid}/appeals/{version}   appeal versions
  share_tokens/{sha256(token)}                     {hid, cid, exp, created_by}
  cost_ledger/{yyyy-mm-dd}                         {inr_estimate, calls, tokens}
  ```
  Composite index: claims by `status` + `updated_at desc` (`infra/firestore.indexes.json`).
  Optimistic concurrency via `update_time` preconditions on claim writes.

### 3.2 Services
- `services/extraction.py` — per document: classify type (cheap Flash call, or the
  user-selected type) then type-specific structured extraction (`PolicyExtraction`,
  `BillExtraction`, `DischargeExtraction`, `InsurerLetterExtraction`). Prompts in
  `prompts/extract_<type>.v1.md` instruct: transcribe, don't compute; amounts as printed
  strings; keep clause numbers verbatim; give `source_page` and `confidence` per line.
  Run documents concurrently (`asyncio.Semaphore(3)`).
- `services/reconcile.py` — convert to paise, compare line-sum to printed total (flag
  mismatch), map extraction → `ClaimFacts`, run the non-payable matcher.
- `services/redaction.py` — deterministic: regexes + Verhoeff check for Aadhaar-like numbers,
  PAN, phone (+91 / 10-digit), email, policy/member/UHID/IP numbers, names from the extracted
  patient/attendant fields, address lines. Replace with stable pseudonyms (HMAC of value with a
  per-hospital salt from Secret Manager). Returns `RedactionReport {counts_by_type}` for the UI
  badge. Optional Sensitive Data Protection pass behind `ARZI_USE_DLP=true` (Phase 7).
- `services/pipeline.py` — `PipelineStep` protocol (`name`, `async run(ctx) -> ctx`) and a
  runner that emits events. Steps for now: `extract → reconcile → redact → audit(rules engine)`.
  Phase 4 composes the reasoning steps with ADK behind the same event contract.
- `services/cost_ledger.py` — per-call ₹ estimate from `usage_metadata` × price table; per-run
  totals stored on the run; daily ledger with a transactional increment; budget guard raises
  `BudgetExceeded` before a live call when the day is over cap.

### 3.3 API (`/api/v1`, all JSON, problem+json errors, request ID header)
```
POST   /claims                               create {mode, insurer_hint?} → ClaimRecord (draft)
GET    /claims?status=&mode=&q=&cursor=      paginated worklist (cursor-based)
GET    /claims/{cid}                         full record
POST   /claims/{cid}/documents               multipart upload (≤ 20 MB/file, PDF/JPEG/PNG, ≤ 30 pages)
GET    /claims/{cid}/documents/{did}/url     signed view URL
POST   /claims/{cid}/consent                 {given_by, purpose}
POST   /claims/{cid}/runs                    start audit (Idempotency-Key) → {run_id}
GET    /claims/{cid}/runs/{rid}/events       SSE: stage.started|stage.completed|flag.created|run.completed|run.failed
PATCH  /claims/{cid}/lines/{line_id}         human correction (category/amount/confirm) → re-runs engine only (no LLM) → new totals
GET    /meta/citations                       citation registry for the UI
```
- SSE: `text/event-stream`, heartbeat every 15 s, event IDs so the client can resume with
  `Last-Event-ID` (events are persisted on the run doc). The request stays open while the
  pipeline runs, so Cloud Run keeps CPU allocated without always-on billing.
- Auth dependency is a pluggable `AuthVerifier`; this phase uses `DemoAuthVerifier` (fixed
  demo user, `hospital_id=sanjeevani-ahd`) behind `ARZI_AUTH_MODE=demo`.

### 3.4 Tests
Integration tests with fakes/replay: upload → run → SSE sequence → persisted record equals
`expected.json` for cases A, B, C. Redaction fixture tests. Budget guard test. Problem-response
shape tests. Cross-tenant access test (another `hospital_id` gets 404).

**Gate:** in `live` mode, case A's scanned bill + policy + discharge summary extract and audit to
`expected.json` values (record the run into `llm_cache`) · replay mode reproduces it offline ·
cost per claim for case A is recorded in `docs/PROGRESS.md` · coverage ≥ 85%.

**Commits:** `feat(adapters): add vertex gemini client with record/replay` →
`feat(adapters): add gcs and firestore repositories` → `feat(extraction): …` →
`feat(redaction): …` → `feat(pipeline): add streamed audit runs` → `feat(cost): add ledger and
budget guard` → `test(api): add end-to-end pipeline tests`.

---

## Phase 4 — ADK agents, guardrails, appeal drafting, sign + export

**Goal:** Google ADK is load-bearing: a multi-agent pipeline whose LLM steps are grounded,
whitelisted and amount-safe, ending in a human-signed appeal PDF.

### 4.1 ADK composition (`arzi/agents/`)
Check the installed `google-adk` version's docs for `SequentialAgent`, custom agents
(subclass `BaseAgent`, implement `_run_async_impl`), `LlmAgent(output_schema=…)`,
`Runner` + `InMemorySessionService`, and Vertex configuration
(`GOOGLE_GENAI_USE_VERTEXAI=TRUE`, project, location).

```
ArziAuditPipeline (SequentialAgent)
 ├─ DocumentExtractor   custom BaseAgent → services.extraction (parallel Gemini structured calls)
 ├─ Redactor            custom BaseAgent → services.redaction (deterministic)
 ├─ PolicyInterpreter   LlmAgent, output_schema=PolicyTerms — maps caps, co-pay, sub-limits,
 │                      waiting periods, associated-expense definition to clause IDs from the
 │                      redacted policy text; low-confidence terms marked for confirmation
 ├─ RulesEngine         custom BaseAgent → arzi.rules.audit (deterministic ₹)
 └─ FlagExplainer       LlmAgent, output_schema=FlagNarratives — plain-language explanation and
                        fix text per flag, citations ⊆ allowed_refs, money only via placeholders
On demand:
 ├─ AppealDrafter       LlmAgent, output_schema=AppealDraft (forum-specific)
 ├─ FamilyExplainer     LlmAgent, output_schema=FamilyExplanation (gu/hi/en) — Phase 6
 └─ ClaimCopilot        LlmAgent with tools get_flags, get_clause, what_if(room_category) → engine (Could)
```
- Session state keys are typed constants (`STATE_FACTS`, `STATE_FLAGS`, …). ADK events map 1:1
  to the Phase 3 SSE contract, so the frontend does not change.
- **Fallback (time-box 45 min):** if ADK composition fights you, keep the Phase 3 runner for
  the pipeline and use ADK for `PolicyInterpreter`, `FlagExplainer` and `AppealDrafter`.
  Record the decision in an ADR.

### 4.2 Guardrails (`arzi/agents/guardrails.py`)
- `validate_citations(output, allowed_refs)`; `validate_amounts(text)` — reject currency
  patterns with digits in en/hi/gu that are not placeholders (₹, Rs., INR, rupees, रुपये/रु.,
  રૂપિયા/રૂ.), allowing digits that are clause numbers, dates or IDs present in context.
- `render_placeholders(text, engine_result, locale)` — en-IN formatting; Gujarati/Hindi
  output keeps Latin digits by default (configurable).
- On validation failure: one automatic retry with the validator message appended; second
  failure → step marked `needs_review` with the raw draft hidden behind a warning.
- Unit tests with adversarial outputs (invented circular, made-up amount, Hindi amount in
  words with digits).

### 4.3 Appeals (`services/appeal.py`, `prompts/appeal_<forum>.v1.md`)
- Structure (from `docs/context/02` §5): addressee and forum → policy and claim numbers →
  facts (admission dates, amounts claimed/approved) → each disputed item (amount placeholder,
  insurer's reason, why it is wrong, citations) → relief sought (placeholder total) →
  enclosures → "Reviewed and signed by" + date.
- Forum rules from `docs/context/03`: GRO first; Bima Bharosa tracking; Ombudsman only after a
  rejection/unsatisfactory reply/no reply within 1 month, within 1 year, claim ≤ ₹50 lakh,
  free — rendered as a checklist, and the Ombudsman option is disabled with a reason when not
  eligible. Insurer response window shown as "about 15 days (verify)".
- Endpoints:
  ```
  POST /claims/{cid}/appeals                  {forum} → draft v1 (runs AppealDrafter)
  PUT  /claims/{cid}/appeals/{v}              edit sections (locked amounts stay placeholders) → new version
  POST /claims/{cid}/appeals/{v}/submit       → in_review
  POST /claims/{cid}/appeals/{v}/sign         {reviewer_name, role, declaration: true} → signed, sha256
  GET  /claims/{cid}/appeals/{v}/export.pdf   only when signed
  ```
- PDF via WeasyPrint with a fictional hospital letterhead, page numbers, the content hash and
  the line "Prepared with Arzi decision support; reviewed and signed by <name>". Fonts embedded
  for gu/hi.
- Every action writes an audit event `{ts, actor, action, version, hash?}`.

**Gate:** case B produces a GRO appeal whose disputed items, citations and relief equal
`expected.json`; case C produces an appeal citing `IRDAI_PED_36M` · guardrail tests pass ·
export is impossible before signing (API test) · signed PDF opens and shows the hash ·
recorded responses in `llm_cache` so replay mode demos all three cases.

**Commits:** `feat(agents): compose audit pipeline with adk` → `feat(agents): add citation and
amount guardrails` → `feat(appeal): add forum-specific drafter` → `feat(appeal): add review,
signing and versioning` → `feat(export): add signed appeal pdf`.

---

## Phase 5 — Desk web app (enterprise UI)

**Goal:** a polished claims-operations product for the hospital TPA desk. Follow
`AGENTS.md §6` exactly. Build the design system first, then screens.

### 5.1 Foundation
- Tokens, Tailwind theme, fonts, shadcn/ui components themed to the tokens (Button, Input,
  Select, Dialog, Sheet, Tabs, Tooltip, Popover, DropdownMenu, Badge, Table, Toast via sonner,
  Command, Skeleton, Progress, Alert).
- Arzi primitives in `web/src/components/`: `Money` (paise → en-IN, tabular, optional accent
  for at-risk), `StatusPill`, `SeverityDot`, `CitationChip` (ref + popover with quote, source,
  Verified/Verify badge), `ConfidenceMark`, `RedactionBadge`, `KpiTile`, `EmptyState`,
  `ProblemAlert` (shows request ID), `PageHeader`, `DataTable` (TanStack: sorting, column
  visibility, sticky header, keyboard row navigation, density toggle), `PipelineProgress`
  (SSE-driven stage list with timings).
- API layer: generated OpenAPI types, a typed fetch wrapper with problem+json parsing, TanStack
  Query hooks per resource, an SSE hook with resume.
- App shell: collapsible sidebar (Worklist, New audit, Appeals, Analytics, Settings), top bar
  (hospital name, "Synthetic data" environment badge, ⌘K command palette, user menu),
  breadcrumb, footer disclaimer.

### 5.2 Screens
1. **Sign-in** — split layout: cream brand panel (logo, tagline "Your claim, defended before
   and after the insurer says no.", three proof points) and a form panel (Google sign-in,
   email/password, "Continue with demo workspace"). Link to the free family check.
2. **Worklist** — KPI strip (claims today, ₹ at risk, ₹ recoverable, median audit time);
   saved-view tabs ("Discharge today", "Needs review", "Appeals in review", "All"); filter bar
   (status, insurer, mode, date range, search); table columns: Claim ID (mono), Patient
   (pseudonym), Insurer/TPA, Mode, Billed, At risk (accent), Flags (severity dots + count),
   IRDAI clock (countdown chip against the 3 h discharge target, tooltip citing
   `IRDAI_CASHLESS_TAT` with its Verify badge), Status, Updated, row menu. Empty state with a
   "Load demo cases" action.
3. **New audit** — 3-step wizard: choose mode (three cards with what each needs) → upload
   (drag-and-drop, per-file progress, detected type chip editable, required-docs checklist per
   mode, consent checkbox stating purpose) → review & run. On run, route to the workspace and
   stream progress.
4. **Claim workspace** (the hero screen) —
   - Header: claim ID, patient pseudonym, insurer, admission → discharge, status, actions
     (Re-run, Share with family, Draft appeal), `RedactionBadge`.
   - Money band: Billed · Predicted payable · At risk · Recoverable on appeal, plus a single
     horizontal stacked bar splitting billed into payable and each deduction type.
   - Split view: left **document viewer** (pdf.js, thumbnails, page jump, text search;
     clicking a bill line or flag jumps to `source_page` and highlights the matching text);
     right **tabs**:
     - *Flags* — cards sorted by ₹ at risk: severity, rule title, amount, explanation, citation
       chips, **Fix** with savings, "Show the maths" (computation trace), Accept/Dismiss (with
       reason, audited). `J/K` to move between flags.
     - *Bill lines* — editable table: description, category (select), amount, qty, confidence,
       IRDAI list, prorated?, payable, deduction. Edits call `PATCH …/lines` and totals update
       in < 300 ms (engine only). Low-confidence rows highlighted with "Confirm".
     - *Policy terms* — extracted caps/co-pay/sub-limits/waiting periods with clause refs and
       confidence; confirm or correct.
     - *Activity* — audit log timeline and pipeline runs (stage durations, model, prompt
       version, tokens, **₹ cost of this audit**).
5. **Appeal editor** — forum selector with eligibility checklist; section-based editor (each
   section editable; amounts render as locked chips from engine values); right rail: citations
   used (with Verify count that must be acknowledged before submitting), enclosures checklist,
   version history; **Review & sign** dialog (reviewer name, role, declaration checkbox) → shows
   content hash → Export PDF / Copy text. Banner: "Draft — not reviewed" until signed.
6. **Appeals list** — table of drafts/in-review/signed/exported with forum and amount sought.
7. **Settings** — hospital profile, room categories and rates (feeds `category` caps), team
   and roles (Phase 7), data and privacy (retention, consent log), system (LLM mode indicator,
   model IDs, prompt versions, daily budget usage).

### 5.3 Quality
- Every screen: loading skeleton, empty, error, success states. Responsive down to 1280 px for
  desk screens.
- Vitest: `Money` formatting (en-IN lakhs/crores), DataTable sorting, appeal sign gate, SSE
  hook reconnection. Playwright (replay mode): journey A (upload → stream → flags → fix),
  journey B (appeal → sign → PDF download), journey C (rejection → appeal) with axe checks.
- Production build served by FastAPI (`StaticFiles` + SPA fallback for client routes) from the
  same container; long cache headers for hashed assets, no-cache for `index.html`.

**Gate:** three Playwright journeys green · axe: zero serious/critical · Lighthouse desktop ≥ 90
(performance, accessibility) on worklist and workspace · screenshots saved to `docs/screens/`
for the deck and README.

**Commits:** `feat(web): add design tokens and primitives` → `feat(web): add app shell` →
`feat(web): add worklist` → `feat(web): add new audit wizard` → `feat(web): add claim workspace`
→ `feat(web): add appeal editor and signing` → `test(web): add e2e journeys`.

---

## Phase 6 — Family experience: multilingual explainer, voice, share link

**Goal:** the family understands what was cut, why, and what to do next — in their language,
by voice — without reading a policy.

1. `FamilyExplainer` agent → `FamilyExplanation {lang, headline, what_happened[], why[],
   next_steps[], reassurance}` using placeholders for every amount; prompt
   `prompts/family_explain.v1.md`: spoken register, short sentences, no jargon (glossary maps
   "proportionate deduction" → plain words per language), always ends with the human-review note.
   Guardrails as in Phase 4. Generated for gu, hi, en; cached on the claim.
2. **Narrated audio:** Gemini TTS model (from `ARZI_MODEL_TTS`; confirm Gujarati and Hindi
   support in the model docs) synthesises each language once; stored in GCS; served via signed
   URL. Fallback adapter: Cloud Text-to-Speech `gu-IN` / `hi-IN` / `en-IN` voices. The adapter
   choice is recorded on the explanation.
3. **Share link:** `POST /claims/{cid}/share` → random 32-byte token (only its hash stored),
   7-day expiry, revocable; `GET /family/{token}` returns the redacted family view model only.
4. **Family page** `/f/:token` — mobile-first, cream surface, language switcher (ગુજરાતી /
   हिन्दी / English) remembered per device, big plain numbers, "Listen" audio player with
   playback speed, next-steps checklist, hospital desk contact, privacy note, disclaimer.
   Fonts load per script. Works on a 360 px screen with large tap targets.
5. **Free "Check my rejection"** `/check` — public: upload rejection/deduction letter + policy,
   consent, rate-limited (per IP, per day) and budget-guarded; result = family explanation +
   "Download a draft appeal (review it before sending)". Creates a claim under a `public`
   tenant with 7-day retention.
6. **(Should) Live Q&A:** "Ask a question" opens a Gemini Live session through a FastAPI
   WebSocket proxy to the Live API on Vertex AI (keys never reach the browser). System prompt
   is grounded in the family explanation + flags; it must not state amounts beyond the provided
   ones. Push-to-talk UI with transcript. If Live is unavailable or Wi-Fi is poor, the button
   falls back to the narrated audio and a text answer.

**Gate:** case C share link opens on a phone viewport, Gujarati audio plays, Hindi and English
switch instantly · amount guard tests pass for gu/hi · `/check` works end to end in replay mode ·
rate limit and budget guard tested.

**Commits:** `feat(family): add multilingual explainer agent` → `feat(voice): add narrated
audio with tts` → `feat(family): add share links and family page` → `feat(family): add public
rejection check` → `feat(voice): add live q&a proxy`.

---

## Phase 7 — Production hardening

**Goal:** the things an enterprise buyer and a technical judge will probe.

1. **Auth + roles:** Firebase Auth on the web (Google + email/password); backend verifies ID
   tokens (`firebase-admin`), reads custom claims `{hospital_id, role}` with roles
   `desk_executive`, `reviewer`, `admin`. Only `reviewer`/`admin` can sign. A seed script sets
   claims for demo users. `ARZI_AUTH_MODE=demo` remains for local dev and a "demo workspace"
   button that issues a short-lived session for the demo tenant.
2. **Tenancy tests:** every endpoint × wrong tenant → 404; role tests for sign/export.
3. **Security:** CSP, HSTS, X-Content-Type-Options, Referrer-Policy, frame-ancestors none;
   strict CORS (same origin); upload validation (magic bytes, size, page count, PDF without
   JavaScript); request size limits; per-user and per-IP token-bucket rate limits (documented
   as per-instance at the current scale); secrets only from Secret Manager; dependency audit
   (`pip-audit`, `npm audit --omit=dev`) in CI.
4. **Privacy:** PII-scrubbing log filter (tested); consent required before any run; retention
   job endpoint (Cloud Scheduler is optional — document it); data export/delete endpoints per
   claim for DPDP requests; `docs/privacy.md` describing data flows and region.
5. **Observability:** structured JSON logs with `logging.googleapis.com/trace` correlation;
   OpenTelemetry tracing to Cloud Trace around each pipeline stage and LLM call; a
   `/api/v1/meta/status` endpoint showing build SHA, model IDs, LLM mode and budget usage.
6. **Evals:** `evals/run.py` over demo cases (live or replay): extraction field accuracy (by
   field type), bill-line category accuracy, flag precision/recall, ₹ exact-match rate,
   guardrail violation count, median latency, ₹ cost per claim → `evals/report.md`.
7. **Optional, flag-gated:** Sensitive Data Protection (DLP) redaction pass
   (`ARZI_USE_DLP=true`); Document AI OCR fallback for pages with low extraction confidence
   (`ARZI_USE_DOCAI=true`). Enable only if the budget allows and record the cost.

**Gate:** auth works on the deployed URL · tenancy and role tests green · security headers
verified with curl · eval report generated with numbers copied to `docs/PROGRESS.md` for the
pitch ("X/Y deductions caught", "₹N per claim").

---

## Phase 8 — Analytics + insights (Could)

1. Per-claim summary rows maintained on audit/appeal events (Firestore aggregate docs per
   hospital per day) — no BigQuery required for the event.
2. `/analytics` page: KPI tiles (claims audited, ₹ at risk found, ₹ recovered, avg cost per
   audit), bar chart ₹ at risk by rule, bar chart by insurer (fictional), trend line by week,
   recovery funnel (at risk → appealed → signed → recovered), cost-per-claim chart.
3. (Stretch) stream summary rows to BigQuery (`arzi_analytics.claim_summaries`, dataset in
   `asia-south1`) and describe the Looker Studio dashboard as roadmap unless built.

**Gate:** analytics page populated from the demo data with all states handled.

---

## Phase 9 — Release, rehearsal, docs, submission

1. **Deploy:** `make deploy` with `ARZI_LLM_MODE=live`, budget guard on. Smoke test the three
   journeys on the Cloud Run URL. Set `--min-instances=1` only for the pitch window and revert
   afterwards (put both commands in `docs/runbook.md`).
2. **Demo reliability:** `replay` mode toggle in Settings (admin only) and as an env flip;
   seed script loads the three demo cases into the demo tenant; Playwright smoke against prod.
3. **Docs:** `README.md` (pitch, screenshots, architecture diagram, quick start, tests and eval
   numbers); `docs/architecture.md` with a **Live vs roadmap** table:
   - *Live:* Gemini multimodal extraction on Vertex AI, ADK multi-agent pipeline, deterministic
     rules engine, citation + amount guardrails, Firestore + Cloud Storage in Mumbai, Cloud Run,
     Gemini TTS (and Live if shipped), Firebase Auth, Cloud Logging/Trace, cost-per-claim ledger.
   - *Roadmap (state honestly):* Gemma redaction inside the hospital's own GCP project, Vertex
     AI Search grounding over policy wordings and circulars, Vertex AI Agent Engine runtime,
     VPC Service Controls per hospital, BigQuery + Looker Studio, NHCX (FHIR) intake, WhatsApp
     intake, Terraform onboarding.
   - `docs/demo-script.md` aligned with `docs/context/04` (75-second flow) and
     `docs/runbook.md` (deploy, rollback, kill switches, billing switch, warm-up).
4. **Pitch numbers:** copy measured eval accuracy and ₹ cost per claim into the pitch
   placeholders (owner updates the deck).
5. **Backup:** record a screen video of the full demo; export cached JSON; keep the replay
   build runnable locally (`make dev`).
6. **Final checks:** `make check` and e2e green on `main`; `git log` contains no attribution
   trailers; no tool-specific files tracked (`git ls-files` review); tag `v0.1.0-buildathon`.

**Gate:** deployed URL works end to end on a phone and a laptop · backup video recorded ·
repository is clean, documented and submitted before the deadline.

---

## Environment variables (all in `config.py`, documented in README)

| Var | Default | Notes |
|---|---|---|
| `ARZI_ENV` | `local` | local, cloud |
| `GOOGLE_CLOUD_PROJECT` | — | |
| `ARZI_GCP_REGION` | `asia-south1` | storage, Firestore, Cloud Run |
| `ARZI_VERTEX_LOCATION` | `asia-south1` | `global` if the model isn't regional |
| `ARZI_MODEL_FLASH` / `_PRO` / `_TTS` / `_LIVE` | — | set from `make models`; never hard-coded |
| `ARZI_LLM_MODE` | `replay` locally, `live` in cloud | live, replay, fake |
| `ARZI_AUTH_MODE` | `demo` locally | demo, firebase |
| `ARZI_BUCKET` | — | |
| `ARZI_DAILY_BUDGET_INR` | `150` | budget guard |
| `ARZI_PRICE_TABLE_JSON` | — | per-model token prices; verify against the current pricing page |
| `ARZI_USE_DLP` / `ARZI_USE_DOCAI` | `false` | optional services |
| `ARZI_PSEUDONYM_SALT_SECRET` | — | Secret Manager resource name |

---

## `docs/PROGRESS.md` template

```markdown
# Progress

## Status
| Phase | State | Gate passed | Notes |
|---|---|---|---|
| 0 | not started | | |
...

## Decisions
- YYYY-MM-DD — <decision> — <why> (ADR-NNNN if any)

## Model choices
- Flash: <id> (checked YYYY-MM-DD, location) · Pro: · TTS: · Live:

## Measured numbers (for the pitch)
- Cost per claim (case A, live): ₹
- Eval: extraction field accuracy %, flags caught X/Y, ₹ exact-match %
- Median audit time: s

## Deviations from plan
## Follow-ups
## Known issues
```
