# Progress

## Status
| Phase | State | Gate passed | Notes |
|---|---|---|---|
| 0 | done | 2026-11-20 | Repo, tooling, hook, CI, GCP bootstrap, budget, model choice, Cloud Run deploy (replay mode). |
| 1 | done | 2026-11-20 | Paise money, claim models, state machine, 12-rule engine with trace, citation whitelist, matcher, CLI; goldens A/B/C exact. |
| 2 | done | 2026-11-20 | Generator for 3 cases: 20 PDFs + scanned JPG, facts/expected/identifiers JSON, README; byte-stable. |
| 3 | done | 2026-11-20 | Upload → SSE-streamed audit → persisted claim; live (Vertex AI; AI Studio for testing) / replay / fake LLM modes; redaction; reconcile; cost ledger + budget guard; Firestore/GCS adapters. Recorded A, B, C replay. |
| 4 | done | 2026-11-20 | ADK Workflow audit (policy interpreter + flag explainer as guarded LlmAgents), citation whitelist + amount guard, forum-specific AppealDrafter, versioned review/sign with SHA-256, signed PDF export, forum checklist. Recorded A, B, C replay. |
| 5 | not started | | Desk web app |
| 6 | not started | | Family experience |
| 7 | not started | | Production hardening |
| 8 | not started | | Analytics |
| 9 | not started | | Release and submission |

### Phase 0 gate
| Check | Result |
|---|---|
| `make setup && make check` green | pass (46 API tests, 100% coverage; rules gate 100%; 3 web tests; lint, mypy strict, tsc clean) |
| commit-msg hook rejects a co-author trailer | pass (throwaway commit rejected, exit 1) |
| `/healthz` 200 from the Cloud Run URL | pass via `/health`: service `arzi` at https://arzi-<project-number>.asia-south1.run.app; `/readyz` 200 with Firestore and Storage checks ok (proves runtime IAM). `/healthz` itself is reserved by the run.app front end (see Deviations) |
| Budgets visible | pass: existing owner budget "Varuna budget" (₹100/month, 50/90/100%) is filtered to this project; owner chose to reuse it instead of creating `arzi-cap-owner` |
| Model choice recorded | pass (see Model choices) |

### Phase 1 gate
| Check | Result |
|---|---|
| 100% line + branch coverage on `arzi.rules` | pass (126 rules tests; also 100% overall across 346 API tests) |
| mypy strict clean | pass (66 files, zero `type: ignore` outside two deliberate wrong-type tests) |
| Golden tests A, B, C | pass: A billed ₹2,25,500 / payable ₹1,57,612.50 / at risk ₹67,887.50 / fix ₹46,875, exactly 4 flags; B payable ₹1,58,512.50, recoverable ₹20,137.50 (₹19,237.50 + ₹900); C `WAITING_REJECTION_INVALID`, relief ₹3,10,000 |
| `python -m arzi.rules.cli demo_cases/case_a/facts.json` | pass (`make rules-demo CASE=case_a`; from the root: `uv run --project api python -m arzi.rules.cli demo_cases/case_a/facts.json`) |
| `make check` green | pass (recipes run directly: `make` is not on this machine's PATH) |

### Phase 2 gate
| Check | Result |
|---|---|
| `make demo-cases` regenerates byte-stable PDFs | pass: a test regenerates all cases and byte-compares every PDF and JSON; the scan JPG is compared within a pixel tolerance |
| PDFs open and look like real documents | pass: reviewed rendered pages (bill, policy schedule, deduction letter, discharge summary, scan) |
| Engine on each `facts.json` equals `expected.json` | pass; hand-checked against the plan: A ₹67,887.50 / fix ₹46,875, B ₹20,137.50, C ₹3,10,000, letter B ₹2,26,500 - ₹88,125 = ₹1,38,375 |
| `make check` green | pass (373 API tests, 100% coverage; rules gate 100%; web lint/types/tests) |

### Phase 3 gate
| Check | Result |
|---|---|
| Live: case A (scanned bill + policy + discharge summary + reports + implant invoice) extracts and audits to `expected.json`, recorded into `llm_cache` | pass, with live Gemini via AI Studio (free tier, testing only, per owner): ₹67,887.50 at risk from the photographed bill. B (₹20,137.50 recoverable) and C (₹3,10,000) also pass live and are recorded |
| Replay reproduces it offline | pass: `record_demo.py case_a case_b case_c --replay`, plus an API integration test in replay mode for all three cases |
| Cost per claim for case A recorded here | ₹0 on the AI Studio free tier. Tokens: 8,765 input / 2,807 output over 10 calls, about ₹3.1 at the Vertex AI standard rate (₹135/₹675 per 1M, assumed ₹90/USD) and about ₹1.5 at today's introductory rate. See Measured numbers |
| Coverage ≥ 85% | pass: 99% (513 API tests); rules gate still 100% |

### Phase 4 gate
| Check | Result |
|---|---|
| Case B produces a GRO appeal whose disputed items, citations and relief equal `expected.json` | pass: items `SUBSUMED_ITEM` ₹900 and `PROP_WRONGLY_APPLIED` ₹19,237.50 (the engine's appealable disputes, in order), each carrying its `expected.json` citations, relief ₹20,137.50. Checked in fake mode and on the recorded Gemini draft (`test_recorded_gemini_responses_replay_to_expected_values`, `record_demo.py --replay`) |
| Case C produces an appeal citing `IRDAI_PED_36M` | pass: one item `WAITING_REJECTION_INVALID` ₹3,10,000 citing `IRDAI_PED_36M` and `policy:5.1` |
| Guardrail tests pass | pass: 44 guardrail tests, 24 of them adversarial rejections (₹/Rs./INR/rupees/"/-", lakh and crore, comma-grouped figures, Hindi and Gujarati words and native digits, currency before a placeholder, invented circular code and "circular no.", unknown clause, paragraph numbers, unknown placeholders, citation whitelist), plus retry, needs-review and unavailable paths under ADK |
| Export is impossible before signing (API test) | pass: 409 `appeal-not-signed` for draft and in-review versions; edits after signing make a new unsigned version |
| Signed PDF opens and shows the hash | pass: pypdfium2 opens it and finds `Content SHA-256: <hash>` and the reviewer line on every page; rendered pages reviewed for cases B (2 pages) and C; identical bytes on re-export |
| Recorded responses in `llm_cache`; replay demos all three cases | pass: `record_demo.py case_a case_b case_c --replay` exits 0 offline; every agent step and both appeals `passed` |
| `make check` green | pass (recipes run directly): 607 API tests, 99.15% coverage; rules gate 100% (153 tests); ruff, mypy strict, ESLint, Prettier, tsc, Vitest |

## Decisions
- 2026-11-20 — Record architecture decisions as ADRs (ADR-0001).
- 2026-11-20 — `/readyz` with no GCP project configured reports ready with zero checks: readiness
  means "can serve", and local replay mode needs no cloud. With a project it probes Firestore
  (read ≤ 1 doc) and the bucket (list ≤ 1 object): the cheapest calls the least-privilege runtime
  identity may make, so a pass also proves the IAM wiring.
- 2026-11-20 — Error responses and logs never include exception messages (they can quote document
  text). Unhandled errors log the exception type and stack frames only, with the request ID.
- 2026-11-20 — `infra/deploy.sh` defaults to `ARZI_LLM_MODE=replay` until model IDs are chosen;
  live mode is opt-in per deploy.
- 2026-11-20 — Budget amounts carry their currency (`5USD` event, `500INR` owner by default);
  `budgets.sh` checks each amount against the billing account's currency before creating anything.
- 2026-11-20 — `roles/run.builder` is granted to the default compute service account, which Cloud
  Build uses for `gcloud run deploy --source` in newly created projects.
- 2026-11-20 — Dependency pins forced by peer ranges: TypeScript 5.9 (openapi-typescript needs
  `^5`, typescript-eslint `<6.1`) and ESLint 9 (eslint-plugin-jsx-a11y does not support 10).
- 2026-11-20 — GCP project is `<project-id>` (number <project-number>, existing project). It is
  already billed to the owner's INR account `<owner-billing-account>`; the event credit account
  `<event-credit-account-1>` (USD) reported `open: False` when checked at ~10:55 IST, so the planned
  event-to-owner billing switch is moot and no budget is created on the event account. Pre-existing
  state checked read-only: no Firestore database, buckets, Cloud Run services, GKE/SQL/Composer/
  Dataproc resources; Compute Engine API disabled.
- 2026-11-20 — Budget: reuse the owner's existing "Varuna budget" (₹100/month) already scoped to
  this project, per owner. Its thresholds are 50/90/100% (the plan's 25% step is not set).
- 2026-11-20 — Infra scripts strip CRLF from gcloud output (Windows) and dry runs perform the
  read-only lookups, so `DRY_RUN=1` prints exactly the commands a real run would execute.
- 2026-11-20 — `web/src/api/openapi.json` is committed next to `schema.d.ts` so API contract
  changes show up in review diffs.
- 2026-11-20 — Money is integer paise, computed only by the pure rules engine (ADR-0002).
- 2026-11-20 — Rule order: non-payables → subsumed → room excess → proportionate → ICU cap →
  sub-limits → co-pay → waiting periods/moratorium → insurer comparison → documents. Sub-limits run
  *after* room-rent cuts (plan listed them before): a sub-limit caps what is otherwise admissible,
  so applying it first and prorating afterwards would cut the same rupee twice.
- 2026-11-20 — Proportionate ratio = cap / per-day rate of the dearest room line above the cap.
  The first version blended all room lines (allowed ÷ billed); a Hypothesis property found that a
  higher rate on a cheap, compliant line then *lowered* the cut. Exact `Fraction` arithmetic.
- 2026-11-20 — Flags carry a `kind`: `deduction` (summed into at-risk; Σ = billed − payable),
  `advisory` (exposure with no computed cut: waiting period, missing document, subsumed item before
  filing) and `dispute` (insurer error; `recoverable` summed into recoverable-on-appeal).
- 2026-11-20 — Recoverable amounts are net of co-pay when co-pay is on the admissible amount
  (case B: ₹21,375 → ₹19,237.50) and gross when co-pay is on the claimed amount.
- 2026-11-20 — Fix savings (₹46,875 in case A) are gross of co-pay, cover only fixes that remove the
  cause (room downgrade or upgrade consent), and are offered only before filing.
- 2026-11-20 — `PROP_WRONGLY_APPLIED` claims insurer proportionate cuts on any line the engine
  does not prorate (excluded categories, non-associated lines, or no breach at all). Over-cuts on
  lines the engine also prorates are not claimed yet (follow-up).
- 2026-11-20 — Matcher: every token of the reference alias must fuzzy-match a token in the line
  (rapidfuzz ratio ≥ 90) after removing punctuation, quantities, units and connector words. Stricter
  than a plain token-set ratio, which scores a bare "Charges" 100 against "registration charges".
  A human's confirmed `irdai_list` (including "none") always wins over the matcher.
- 2026-11-20 — Policy clause citations use the form `policy:<clause_id>`, next to whitelist IDs
  such as `IRDAI_PROP_DED_2020`, so the Phase 4 guardrail can tell the two sources apart.
- 2026-11-20 — `scripts/demo_data.py` is the single source for each demo case: `facts.json`,
  `expected.json`, `identifiers.json` and every document are generated from it, so they cannot drift.
- 2026-11-20 — Byte stability: reportlab invariant mode, Bitstream Vera TTFs from the reportlab
  package embedded (no font files in the repo), uncompressed page streams (zlib output differs across
  builds), fixed seed for scan noise. Cost: about 100 KB per PDF, about 2.3 MB in total.
- 2026-11-20 — Documents print "Rs." rather than "₹": Vera has no rupee glyph, and "Rs." is common on
  Indian bills. `to_paise` already parses both.
- 2026-11-20 — `expected.json` holds flags, totals, fix savings and citation statuses, not trace
  wording, so copy edits do not churn fixtures. Citation status values: `verified`, `verify`, `policy`.
- 2026-11-20 — The owner's `IRDA-Non-Medical-Expenses.pdf` was the 2013 non-admissible list (items
  65-199 only), not Lists I-IV, and it calls admission/registration charges non-payable where List IV
  subsumes them. Deleted at the owner's request. The official IRDAI "Modification Guidelines on
  Standardization in Health Insurance" (27 Sep 2019) was downloaded from irdai.gov.in instead
  (`docs/context/irdai/`, SHA-256 in SOURCE.md).
- 2026-11-20 — Non-payable reference data is now all 146 items of Lists I-IV, generated by
  `scripts/parse_non_payable.py` and still `verify` pending owner review. Aliases are conservative:
  conditional items keep only their full wording, aliases must name something specific, and on a tie
  the alias with more words wins ("Face mask" is List II, not the List I "mask"). All 16 demo bill
  lines classify exactly as before, so the goldens are unchanged.
- 2026-11-20 — `match_non_payable` is memoised per description and scores tokens inside rapidfuzz.
  With about 240 aliases, the property tests had hit Hypothesis's 200 ms deadline under coverage.
- 2026-11-20 — Audit runs stream over SSE from the instance that runs them; no queue (ADR-0003).
- 2026-11-20 — Pipeline order is extract → redact → reconcile → audit. The plan put redaction after
  reconcile; redacting first means `ClaimFacts` is never built from raw identifiers.
- 2026-11-20 — Gemini transcribes and classifies only. Amounts are printed strings and enums are
  used for document type, service head and the insurer's reason. Parsing to paise, months of cover,
  cap interpretation and letter-row → bill-line mapping are deterministic code (`reconcile.py`);
  anything unsettled becomes a "needs confirmation" `ReviewIssue`.
- 2026-11-20 — Redaction removes every Aadhaar-shaped number whatever its Verhoeff check digit
  (a mistyped real number is still personal data). The plan used Verhoeff to detect them, but the
  synthetic numbers deliberately fail it. Pseudonyms are HMAC-SHA256 of the value; surname-only
  mentions map to the full name's pseudonym. The original values go to a restricted
  `restricted/identity` document.
- 2026-11-20 — LLM modes: `replay` (real recordings under `demo_cases/*/llm_cache`, keyed by prompt
  version + input hashes, not model ID), `fake` (generator-written ideal extractions keyed by file
  SHA-256), `live` (Vertex AI → budget guard → optional recorder). A replay miss is an error, never a
  silent live call.
- 2026-11-20 — Costs are integer micro-rupees from `ARZI_PRICE_TABLE_JSON`; a live call for an
  unpriced model is refused. The budget day is IST (fixed UTC+05:30; Windows and slim images may
  lack tzdata).
- 2026-11-20 — Claim writes compare `revision` and then `update()` with a `last_update_time`
  precondition (Firestore `set()` takes no precondition).
- 2026-11-20 — Consent is required before a run starts (409 `consent-required`). Audit-log entries
  carry IDs and types only, never file names, which can contain patient names. Failed runs log the
  exception type and frames, never the message: a test caught `logger.exception` leaking it.
- 2026-11-20 — Letter rows map to bill lines by exact normalised text, else a one-way fuzzy match
  accepted only when exactly one line fits; ambiguous rows ("Charges") become `unmapped_deduction`.
- 2026-11-20 — Per the owner, testing and recordings use the Gemini Developer API (AI Studio, free
  tier, key in the git-ignored `api/.env.local`); the deployed app always uses Vertex AI. Enforced in
  code (`ARZI_LLM_PROVIDER=ai_studio` is refused when `ARZI_ENV=cloud`) and in `infra/deploy.sh`
  (pins `ARZI_LLM_PROVIDER=vertex`). The free tier may use prompts for product improvement, so it
  is only ever fed synthetic documents.
- 2026-11-20 — Free-tier availability decided the recording models: `gemini-3.8-flash` returned 503
  (high demand), 3.7 timed out, and 3.6, 3.5 and 2.5 Flash ran out of daily quota partway. The
  recordings mix `gemini-3.6-flash`, `gemini-2.5-flash` and `gemini-3.5-flash-lite`. Replay keys
  exclude the model, so this is fine for replay; extraction quality on Vertex 3.8 Flash should be
  re-checked with `make eval` (Phase 7).
- 2026-11-20 — `extract_policy@v2`: `gemini-2.5-flash` read "10% of admissible claim" as co-pay on the
  claimed amount through the `on_claimed_amount` boolean. The schema now has an explicit
  `applies_to: admissible | claimed` enum, and the prompt says to take it from the policy's
  wording. Superseded v1 recordings were deleted.
- 2026-11-20 — AI Studio uses API version `v1beta` (JSON mode is not enabled on v1 for some models).
  `ARZI_LLM_THINKING_BUDGET=-1` leaves thinking at the model default; flash-lite rejects a zero budget.
- 2026-11-20 — Amounts inside words ("Rs. 40,000.00 per eye") are read only when marked as money
  (₹, Rs, INR), so the "1" of "1% of sum insured" is never one rupee.
- 2026-11-20 — `record_demo.py` serves existing recordings first and calls the model only for missing
  responses, so a rerun after a quota error costs only what is still missing.
- 2026-11-20 — Case C in post-rejection mode relies on the statutory 36-month cap even when the
  rejected condition does not match a declared PED (`min(policy waiting or 36, 36)`).
- 2026-11-20 — The audit is an ADK 2.15 `Workflow` (`SequentialAgent` is deprecated in 2.x), run
  in-process with an in-memory session per run; `LlmAgent`s use a `BaseLlm` bridge over the
  `LlmClient` port so replay, fake, budget guard and cost ledger are unchanged (ADR-0004).
  `google-genai` moved from 3.6 to 2.34 because ADK requires `<3`.
- 2026-11-20 — Reasoning steps never carry the money and never block the audit: a model outage,
  replay miss or budget stop leaves the step `unavailable` and the run still completes. One retry
  with the validator's feedback, then `needs_review` (draft kept, unrenderable text hidden).
- 2026-11-20 — Placeholders, the amount guard and the citation whitelist apply to every model- and
  person-written sentence; prose is stored as `{template, text}` so line corrections re-render
  without a model call (ADR-0005). Rendering also turns ref IDs into readable labels.
- 2026-11-20 — The PolicyInterpreter does not change the facts the engine uses; it is a second
  reading. A clause that disagrees with extraction becomes a `policy_term_unconfirmed` issue,
  confidence below 0.8 marks the term for confirmation.
- 2026-11-20 — Agent inputs exclude claim IDs, timestamps and pseudonyms (which depend on the
  deployment's key), so a recording replays for every run of a demo case.
- 2026-11-20 — Appeals: disputed items are the engine's `dispute` flags that are appealable; their
  amounts, the insurer's reason (fixed wording, never the letter's own text, which can quote
  amounts) and the relief total are deterministic; the model writes subject, facts, one argument per
  item and the relief sentence. Item citations are the engine's refs plus any whitelisted refs the
  model added.
- 2026-11-20 — Versions are immutable; only the latest can be edited, submitted or signed. Edits are
  rejected (422) rather than retried when they break the guardrails. Only a draft whose prose passed
  its checks and has text in every section can go to review.
- 2026-11-20 — The SHA-256 covers the rendered letter content (claim, version, forum, subject,
  facts, items, relief, enclosures). Identity fields come from the restricted vault only when the
  PDF is printed and are not part of the hash; the export re-checks the hash before printing.
- 2026-11-20 — `GET .../export.pdf` moves a signed appeal to `exported` on first call; later calls
  reprint the same bytes. Idempotent, so a GET is acceptable; the audit log records one export.
- 2026-11-20 — Forum eligibility is deterministic (`rules/forums.py`): GRO and Bima Bharosa are
  always open; the Ombudsman needs a written complaint first, a rejection or unsatisfactory reply or
  a month without one, filing within a year of that, and an amount in dispute up to ₹50 lakh. The
  GRO window is shown as "about 15 days (verify)".
- 2026-11-20 — Signed PDFs use reportlab with embedded IBM Plex fonts (OFL), not WeasyPrint, which
  needs Pango and could not be built or tested on the development machine (ADR-0006).
- 2026-11-20 — Reasoning agents default to a 1024-token thinking budget and an 8192-token output
  cap: with the model's default budget the policy interpreter's JSON came back truncated.

## Model choices
Checked 2026-11-20 with `make models` (listing only; first real call is in Phase 3). Rule: newest of
each tier, `asia-south1` if served there, otherwise `global`.
- Flash: `gemini-3.8-flash` (global) · regional fallback `gemini-3.5-flash` (asia-south1)
- Pro: `gemini-3.1-pro-preview` (global) · GA fallback `gemini-2.5-pro`; Pro only where an eval needs it
- TTS: `gemini-3.8-flash-tts` (global) · Gujarati/Hindi support to confirm in Phase 6
- Live: `gemini-3.8-live` (asia-south1)
- Not chosen: `gemini-4-*` IDs (codenames with no tier in the name; revisit with docs).

## Measured numbers (for the pitch)
- Cost per claim (case A, live): 8,765 input + 2,807 output tokens over 10 Gemini calls; ₹0 on the AI Studio free tier, about ₹3.1 at the Vertex AI standard rate (₹1.5 at the introductory rate). Measured on free-tier Flash models; re-measure on Vertex `gemini-3.8-flash` before quoting it on stage.
- Agents (recorded, free-tier models): policy reading about 1,320 in / 550-780 out tokens; flag
  explanations 2,000-4,100 in / 140-1,000 out (+ up to 1,200 thinking); GRO appeal 2,200-3,000 in /
  320-580 out (+ about 1,200 thinking). Case A audit including agents: 13,423 in / 4,133 out over
  12 calls, about ₹4.6 at the Vertex AI standard rate (₹3.1 extraction + ₹1.5 agents); case B appeal
  about ₹1.5. Re-measure on Vertex `gemini-3.8-flash`.
- Eval: extraction field accuracy %, flags caught X/Y, ₹ exact-match %
- Median audit time: s

## Deviations from plan
- Task 0.1.10 (copy logo): `web/public/brand/arzi-logo.png` was already in place.
- Commit "chore(infra): first cloud run deploy" became "chore(infra): add cloud run deploy": the
  deploy itself is an owner action. Model discovery got its own commit,
  "feat(api): add vertex model discovery".
- Google's front end reserves `/healthz` on `*.run.app` URLs (returns its own 404 without reaching
  the container). `/healthz` stays for Cloud Run's container probes; `/health` is the external
  alias used by the deploy smoke test and uptime checks.
- The first deploy attempt failed on a local DNS error during source upload (network, not code);
  the retry succeeded. The upload is 45 files (~0.5 MB) thanks to the `.gcloudignore` allow-list.
- `make test-e2e` is wired (Playwright + axe smoke on the placeholder page) but was not run in
  Phase 0 because it downloads Chromium; the e2e journeys arrive in Phase 5.
- Phase 1 model shape: room-rent cap is a discriminated union (`per_day_amount` / `pct_of_si` /
  `category`, each with its own typed field) instead of `{type, value}`; `icu_cap_per_day` became
  `icu_cap {amount_per_day, clause_id}`; trace steps are `TraceStep`. `days_room`/`days_icu` are not
  stored: room and ICU days are the `qty` of their bill lines.
- Phase 1 seeded `demo_cases/case_{a,b,c}/facts.json` (engine inputs, needed for the CLI gate).
  Phase 2 generates the PDFs and `expected.json` from them.
- Non-payable seed skips "service charges where nursing is also charged" (conditional on another
  line, so a plain alias would cut "ambulance service charges"), and gloves, masks, admission kits
  and attendant charges (the brief names them without saying which list they are on).
- Phase 2: `pypdfium2` (Google's PDFium) is a third dev dependency next to reportlab and Pillow. It
  rasterises the real bill PDF for the scan instead of re-drawing the layout in Pillow, and it reads
  PDF text in tests.
- Phase 2: added `investigation_reports.pdf` and `implant_invoice.pdf` per case so `documents_present`
  in `facts.json` is true. Clause numbers follow the plan (5.1 PED, 7.4 co-pay, 9.2 documents; 8.1
  non-medical expenses added for the deduction letter), and the hospital is in Ahmedabad.
- Phase 2: no GST lines on the bills. Room rent above ₹5,000/day attracts GST, which would change the
  golden totals; the cases stay as specified.
- Phase 3: Secret Manager for the pseudonym key is deferred. `ARZI_PSEUDONYM_SALT` (SecretStr) is
  read from the environment, with a local-only default; Cloud Run must set it from Secret Manager.
- Phase 3: `pypdfium2` became a runtime dependency (upload page counts). `python-multipart` added
  for uploads.
- Phase 3: fixed a Phase 2 bug found by the end-to-end test. The case A/B policy schedule printed
  "Co-payment 1E+1%" (`str(Decimal(10).normalize())`); all decimal displays now use fixed-point
  formatting, and a regression test checks the printed text.
- Phase 3: added `GET /claims/{cid}/documents`, `.../documents/{did}/content` (streaming fallback
  when GCS cannot sign URLs) and `GET /claims/{cid}/audit-log` beyond the plan's list.
- Commits: one per rule family rather than one per rule, so every commit stays green under the
  100% rules coverage gate.
- Phase 4: ADK `Workflow` instead of `SequentialAgent` (deprecated in ADK 2.x); the ADK fallback
  was not needed. `reconcile` runs as its own node between `redact` and `interpret_policy`.
- Phase 4: reportlab instead of WeasyPrint for the PDF (ADR-0006). Fonts for Hindi and Gujarati are
  not embedded: appeals are in English, and reportlab cannot shape Indic scripts.
- Phase 4: endpoints beyond the plan: `GET /claims/{cid}/appeals/forums` (checklist),
  `GET /claims/{cid}/appeals` and `GET /claims/{cid}/appeals/{v}`. `PUT` returns 201 with the new
  version. `POST /appeals` accepts `gro_complaint` for the Ombudsman checks.
- Phase 4: recordings mix `gemini-3.6-flash`, `gemini-3.5-flash-lite` and `gemini-2.5-flash`
  (free-tier quota; `gemini-3.8-flash` was rate-limited). Replay keys exclude the model.
- Phase 4: fixed a regression from the SDK downgrade found while recording: google-genai 2.x closes
  its transport when the `Client` is garbage-collected, so the factories now keep it alive.

## Follow-ups
- Phase 3: models live in different locations (Flash/Pro/TTS global, Live asia-south1), but
  settings have one `ARZI_VERTEX_LOCATION` (deployed as `global`). Add a per-model location map
  and record the endpoint choice in `docs/architecture.md` (data at rest stays in Mumbai).
- Phase 3: first live call per chosen model confirms access and quota, not just listing.
- Firebase CLI is not installed locally; the scripts and runbook use `npx firebase-tools@latest`.
- Owner: check Billing → Credits for why the event credit account is closed; if it is reopened,
  run `infra/budgets.sh` with `BILLING_ACCOUNT_EVENT` set to add its budget.
- CI: fail when `make openapi` changes `web/src/api/` (schema drift check).
- Move to TypeScript 6+ and ESLint 10 when typescript-eslint, openapi-typescript and
  eslint-plugin-jsx-a11y support them.
- Phase 5: self-host IBM Plex fonts (the placeholder page uses system fallbacks).
- Phase 7: structured JSON logging with trace correlation and a PII-scrubbing filter.
- Owner: review `docs/context/irdai/PARSED_LISTS.md` against the scan, confirm the circular number,
  and check the 2024 Master Circular annexure for changes; then flip the 146 items to verified (steps
  in `docs/context/irdai/SOURCE.md`).
- Rules: List I "AMBULANCE" is cut as not payable, but many policies include a road-ambulance
  benefit. Model policy-specific cover for List I items (not only the all-items add-on flag).
- Rules: conditional List I items ("service charges where nursing charge also charged", "food
  charges other than patient's diet", "oxygen cylinder for usage outside the hospital", "any kit
  with no details") keep only their full wording, so they are effectively never auto-matched. They
  need explicit condition logic or a human hint.
- Rules: claim insurer over-cuts on lines the engine also prorates (needs a rounding tolerance).
- Rules: policy deductible, initial 30-day waiting period, and conditional List I items.
- Rules: `CategoryCap` whose category is missing from the hospital tariff is traced and skipped;
  Phase 3 should surface it as "Needs confirmation" in the UI.

- Re-record the demo cases on Vertex AI `gemini-3.8-flash` before the pitch (run `record_demo.py`
  with `ARZI_LLM_PROVIDER=vertex` and the price table in this file), so replay matches the live
  model; then re-measure cost per claim.
- Rotate the AI Studio key after the event (it was shared in chat).
- Owner, cloud (no cost beyond pennies): deploy `infra/firestore.indexes.json`, run
  `scripts/seed.py` for the demo hospital profile, set `ARZI_PSEUDONYM_SALT` from Secret Manager on
  Cloud Run, and grant the runtime identity `iam.serviceAccountTokenCreator` on itself if signed
  URLs are wanted (otherwise documents stream through the API).
- Phase 3: Docker image now copies `demo_cases/*/llm_cache` and `extraction` (replay/fake in the
  cloud); first built on the next `make deploy`.
- Phase 3: stale-run sweeper for runs left `running` by a dead instance (ADR-0003).
- Phase 3: Firestore worklist search (`q`) scans a bounded window client-side; move to a search
  field or prefix index if volumes grow.
- Phase 4: escalation after export (GRO letter exported, no reply → Ombudsman) needs a state
  transition from `exported`; today an exported claim cannot be appealed again.
- Phase 4: signing is open to any signed-in desk user who names a reviewer; restrict it to the
  `reviewer` role with Firebase Auth (Phase 7).
- Phase 4: give agents dates as "3 October 2026" rather than ISO (the recorded case B facts read
  "2026-10-03"); needs a re-recording.
- Phase 4: treat transport errors (httpx connect/read) as retryable `llm-network` in the Gemini
  client; today only API errors and timeouts are retried.
- Phase 4: map the Ombudsman office from the hospital's city; the letter says "jurisdiction to be
  confirmed".
- Phase 4: the GRO prompt lets the model say "within 15 days"; prefer "about 15 days" while
  `INSURER_GRIEVANCE_15D` is `verify`.
- Phase 4: re-record the agent and appeal responses on Vertex AI with the demo-day model.

## Known issues
- On Windows, `make` needs bash on PATH (Git Bash) because the Makefile sets `SHELL := bash`.
