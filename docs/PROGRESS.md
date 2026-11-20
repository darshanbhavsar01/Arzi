# Progress

## Status
| Phase | State | Gate passed | Notes |
|---|---|---|---|
| 0 | done | 2026-11-20 | Repo, tooling, hook, CI, GCP bootstrap, budget, model choice, Cloud Run deploy (replay mode). |
| 1 | done | 2026-11-20 | Paise money, claim models, state machine, 12-rule engine with trace, citation whitelist, matcher, CLI; goldens A/B/C exact. |
| 2 | done | 2026-11-20 | Generator for 3 cases: 20 PDFs + scanned JPG, facts/expected/identifiers JSON, README; byte-stable. |
| 3 | not started | | Ingestion, extraction, redaction, pipeline |
| 4 | not started | | ADK agents, guardrails, appeals |
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
- 2026-11-20 — Case C in post-rejection mode relies on the statutory 36-month cap even when the
  rejected condition does not match a declared PED (`min(policy waiting or 36, 36)`).

## Model choices
Checked 2026-11-20 with `make models` (listing only; first real call is in Phase 3). Rule: newest of
each tier, `asia-south1` if served there, otherwise `global`.
- Flash: `gemini-3.8-flash` (global) · regional fallback `gemini-3.5-flash` (asia-south1)
- Pro: `gemini-3.1-pro-preview` (global) · GA fallback `gemini-2.5-pro`; Pro only where an eval needs it
- TTS: `gemini-3.8-flash-tts` (global) · Gujarati/Hindi support to confirm in Phase 6
- Live: `gemini-3.8-live` (asia-south1)
- Not chosen: `gemini-4-*` IDs (codenames with no tier in the name; revisit with docs).

## Measured numbers (for the pitch)
- Cost per claim (case A, live): ₹
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
- Commits: one per rule family rather than one per rule, so every commit stays green under the
  100% rules coverage gate.

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
- Rules: `docs/context/irdai/IRDA-Non-Medical-Expenses.pdf` has arrived (untracked). Write
  `scripts/parse_non_payable.py`, load the full Lists I-IV and flip statuses to verified. Needs the
  owner's go-ahead because it changes regulatory data.
- Rules: claim insurer over-cuts on lines the engine also prorates (needs a rounding tolerance).
- Rules: policy deductible, initial 30-day waiting period, and conditional List I items.
- Rules: `CategoryCap` whose category is missing from the hospital tariff is traced and skipped;
  Phase 3 should surface it as "Needs confirmation" in the UI.

## Known issues
- On Windows, `make` needs bash on PATH (Git Bash) because the Makefile sets `SHELL := bash`.
