# AGENTS.md — Arzi engineering handbook

> Read this file completely at the start of **every** session, then read `docs/BUILD_PLAN.md`
> and `docs/PROGRESS.md`. Execute only the phase you were asked to execute. Stop at its gate.

Arzi is an AI health-insurance claims auditor and appeals agent for India. It is a **startup
product**, not a hackathon toy. It will be judged live at Startup Buildathon India 2026
(Google DeepMind × Google Cloud), and the code may be scored by an automated evaluator for
**efficiency, quality, testing, UI and backend design**. Write every line as if a staff engineer
and a senior product designer will review it.

---

## 0. Non-negotiable rules (read twice)

1. **No AI-tool attribution, anywhere.**
   - Never add `Co-Authored-By:` trailers, "Generated with …" footers, robot emojis, or the
     name of any AI coding assistant or its vendor to commits, PR titles/bodies, branch names,
     tags, code comments, docstrings, file names, folder names, logs or docs.
   - The **only** author of every commit is the repo owner (Darshan Bhavsar). Use the git
     identity already configured; never pass `--author`, never edit git config identity.
   - Never create assistant-specific files or dot-directories in the repo. If the tooling
     creates one, it must stay untracked. The owner keeps those patterns in the local,
     untracked `.git/info/exclude` — never add them to `.gitignore` or any tracked file.
     Before every commit, check `git status` and make sure no tool-specific file is staged.
   - The `commit-msg` hook in `.githooks/` rejects any commit containing a co-author trailer
     or tool footer. Never bypass hooks (`--no-verify` is forbidden).
2. **Google-first product stack.** The product runs on Google Cloud and Google AI only:
   Gemini (Vertex AI), Gemini Live / Gemini TTS, ADK, Firestore, Cloud Storage, Cloud Run,
   Firebase Auth (Identity Platform), Cloud Logging/Trace, Secret Manager, optionally
   Document AI, Sensitive Data Protection, BigQuery. Never add a non-Google LLM, vector DB,
   hosting provider or auth provider to the product.
3. **Rupee maths is deterministic.** Every ₹ amount shown, stored, spoken or written in an
   appeal comes from `arzi.rules` (pure Python, integer paise). The LLM extracts, classifies,
   explains, cites and drafts — it never computes money. LLM-generated text may contain
   amounts only via placeholders the server fills from engine output (see §5).
4. **Never invent regulations.** Cite only rule IDs in `rules/data/rule_citations.json` or
   clause IDs extracted from the policy in context. Each citation has a `status` of
   `verified` or `verify`; `verify` is rendered in the UI as an amber "Verify before filing"
   badge. Unknown → say "unverified". Never fabricate a circular number or paragraph.
5. **Human in the loop.** Arzi is decision support. No appeal can be exported or shared until
   a named human reviewer signs it. This framing appears in UI copy, API design and docs.
6. **Privacy (DPDP).** Synthetic data only. Data at rest in `asia-south1` (Mumbai). Patient
   identifiers are redacted before any reasoning/drafting step. Consent and an append-only
   audit log are recorded per claim. No PII in logs, traces, analytics or error messages.
7. **Cost ceiling.** Total cloud spend for the event must stay under **USD 5 credit + ₹500**.
   Scale-to-zero everywhere, Flash-class models by default, budget guard on (see §7).
8. **Model names are configuration.** Never hard-code a Gemini model ID in code. Read from
   settings (`ARZI_MODEL_FLASH`, `ARZI_MODEL_PRO`, `ARZI_MODEL_TTS`, `ARZI_MODEL_LIVE`).
   Run `make models` to list what the project can access and record the choice in
   `docs/PROGRESS.md`.
9. **Fictional brands only.** Demo hospitals and insurers are fictional
   (e.g. "Sanjeevani Multispeciality Hospital", "Suraksha Health Insurance Co. (fictional)").
   Never imitate a real insurer's letterhead, logo or wording.

---

## 1. How to work in this repo

- **One phase per session.** Read the phase in `docs/BUILD_PLAN.md`, restate its goal and
  task list in a short plan, then implement. Do not start the next phase uninvited.
- **Phase gate.** A phase is done only when every acceptance check passes:
  `make check` green (lint + types + tests + coverage), the phase's demo command works, and
  `docs/PROGRESS.md` is updated (what shipped, decisions, deviations, follow-ups).
- **Small, reviewable commits.** Conventional Commits (`feat(rules): …`, `fix(api): …`,
  `test(rules): …`, `chore(infra): …`, `docs: …`). One logical change per commit. Commit at
  every green checkpoint. Branch per phase: `phase/<n>-<slug>`; merge to `main` at the gate.
- **Ask, don't guess, on:** anything that spends money, deletes cloud resources, changes
  billing, changes IAM, or changes a regulatory rule. Everything else: decide, note the
  decision in `docs/PROGRESS.md`, move on.
- **Record architectural decisions** as short ADRs in `docs/adr/NNNN-title.md`
  (context → decision → consequences). Expected ADRs: money as paise, SSE pipeline instead
  of a queue, ADK in-process on Cloud Run, citation whitelist + amount guard, single
  container serving API + SPA.
- **Don't over-build.** If a task is not in the current phase, add it to "Follow-ups" in
  `docs/PROGRESS.md` instead.

---

## 2. Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, Pydantic v2, pydantic-settings, `uv` for deps/venv |
| AI | `google-genai` SDK on **Vertex AI** (`vertexai=True`), Google **ADK** (`google-adk`) in-process |
| Data | Firestore (Native, `asia-south1`), Cloud Storage (`asia-south1`, uniform access, PAP enforced) |
| Auth | Firebase Auth (Identity Platform); backend verifies ID tokens with `firebase-admin` |
| Frontend | Vite + React + TypeScript (strict), Tailwind CSS, shadcn/ui (Radix primitives), lucide-react, TanStack Query, TanStack Table, React Router, react-hook-form + zod, pdf.js viewer, i18next (en/hi/gu), Recharts |
| API contract | FastAPI OpenAPI → `openapi-typescript` generated client types (`web/src/api/schema.d.ts`). Never hand-write API types. |
| Docs/PDF | WeasyPrint (server-side appeal PDF with fictional letterhead) |
| Quality | ruff (lint+format), mypy `--strict`, pytest, pytest-asyncio, hypothesis, coverage; ESLint (typescript-eslint strict), Prettier, Vitest, Testing Library, Playwright, axe-core |
| Deploy | One Cloud Run service (`arzi`, `asia-south1`) serving API + built SPA; `gcloud run deploy --source` |
| CI | GitHub Actions: lint, typecheck, unit tests, build. No cloud credentials in CI. |

Use the latest stable versions at install time and pin them via `uv.lock` / `package-lock.json`.

---

## 3. Repository layout

```
arzi/
  AGENTS.md                      # this file
  README.md                      # product overview, quick start, architecture diagram, live-vs-roadmap
  Makefile                       # the only entry point humans and agents need
  Dockerfile                     # multi-stage: web build → python runtime (non-root)
  .githooks/commit-msg           # rejects co-author trailers / tool footers
  .github/workflows/ci.yml
  docs/
    BUILD_PLAN.md  PROGRESS.md  architecture.md  runbook.md  demo-script.md
    adr/  context/               # context/ = founder's brief, domain rules, pitch, deck text
  api/
    pyproject.toml  uv.lock
    src/arzi/
      main.py                    # app factory, middleware, static SPA mount
      config.py                  # Settings (pydantic-settings), all env vars documented
      api/                       # routers/, deps.py, errors.py (RFC 7807), sse.py
      domain/                    # models.py (Claim etc.), money.py (Paise), enums.py, state.py
      rules/                     # engine.py, rule modules, data/*.json — PURE, no I/O
      services/                  # pipeline, extraction, redaction, appeal, explain, voice, export, cost_ledger
      agents/                    # ADK agents, tools, guardrails (citation + amount validators)
      adapters/                  # genai_client, gcs, firestore_repo, tts, auth — behind Protocols
      observability/             # structured logging w/ PII filter, tracing
      prompts/                   # versioned prompt templates (*.md), loaded by name+version
    tests/  unit/ integration/ fixtures/
  web/
    src/ app/ components/ features/ lib/ api/ i18n/ styles/
    public/brand/arzi-logo.png
    tests/ (vitest)  e2e/ (playwright)
  demo_cases/case_a/ case_b/ case_c/   # synthetic PDFs + expected.json + cached LLM responses
  evals/                         # run.py → evals/report.md (extraction + flag accuracy)
  infra/                         # bootstrap.sh, deploy.sh, budgets.sh, iam.sh, *.json policies
  scripts/                       # gen_demo_cases.py, list_models.py, seed.py
```

---

## 4. Backend engineering standards

- **Layering is strict:** `api` → `services` → (`rules`, `agents`, `adapters`). `rules/` and
  `domain/` import nothing from `adapters`, `api`, FastAPI or any cloud SDK.
- **Ports & adapters.** `ClaimRepository`, `BlobStore`, `LlmClient`, `SpeechClient`,
  `AuthVerifier` are `typing.Protocol`s. Real adapters in `adapters/`; in-memory fakes in
  `tests/fakes.py`. Services receive dependencies via FastAPI `Depends` / constructor
  injection — no module-level singletons that tests cannot swap.
- **Money:** `Paise = NewType("Paise", int)`. Parse once at the boundary from extracted
  strings/numbers using `Decimal`, round `ROUND_HALF_UP` to paise. Never `float` for money.
  Format only in presentation (`en-IN`, e.g. ₹1,57,612.50).
- **Typing:** mypy strict passes with zero `type: ignore` except at third-party boundaries
  (comment why). Pydantic models are `frozen=True` where they are values.
- **Errors:** domain exceptions → RFC 7807 `application/problem+json` with a stable `type`
  slug and a request ID. Never leak stack traces or document text in responses.
- **Async:** I/O is async end-to-end; CPU-light rules run inline. Blocking SDK calls go
  through `anyio.to_thread.run_sync`.
- **Idempotency:** `POST` endpoints that start work accept `Idempotency-Key`.
- **Multi-tenancy from day one:** every repository method takes `hospital_id`; Firestore
  paths are `hospitals/{hid}/claims/{cid}/…`. A test proves cross-tenant reads fail.
- **Prompts are code:** stored in `prompts/<name>.v<N>.md`, versioned, referenced by name +
  version, and the version is recorded on every LLM output in the claim's audit log.
- **LLM calls** always: `temperature` low (0–0.2), structured output via `response_schema`
  (Pydantic) where the output is data, explicit `max_output_tokens`, timeout + 2 retries with
  jittered backoff on 429/5xx only, token usage recorded to the cost ledger.
- **LLM modes:** `ARZI_LLM_MODE=live|replay|fake`. `replay` serves recorded responses from
  `demo_cases/*/llm_cache/` (keyed by prompt version + input hash) — this is the venue-Wi-Fi
  fallback and keeps tests free. `fake` is deterministic stubs for unit tests.
- **Docstrings** on public functions explain *why*, not *what*. No commented-out code. No
  TODOs without a matching entry in `docs/PROGRESS.md` follow-ups.

## 5. AI guardrails (these are product features — show them in the UI and pitch)

1. **Citation whitelist:** every agent receives `allowed_refs` (rule IDs + policy clause IDs
   in context). Output schemas carry `citations: list[str]`; a validator rejects any ref
   not in `allowed_refs` and the step is retried once, then surfaced for human review.
2. **Amount guard:** LLM prose may reference money only as placeholders like
   `{{flag.PROP_ROOM_RENT.amount}}` or `{{totals.at_risk}}`. The server renders them from
   engine output. A validator scans final text for any digit-bearing currency pattern
   (₹, Rs, INR, rupees, रुपये, રૂપિયા) that did not come from a placeholder and fails the step.
3. **Extraction confidence:** each extracted bill line has `confidence` (0–1). Lines < 0.8
   and any bill whose line-sum ≠ printed total are shown as "Needs confirmation".
4. **Redaction before reasoning:** after extraction, patient identifiers (name, phone,
   Aadhaar-like 12-digit, PAN-like, email, policy/member numbers, addresses) are replaced
   with stable pseudonyms (`P-7F3A`) before any downstream agent sees the data. Raw
   identifiers are kept only in a separate restricted field used for the signed letter.
5. **Human sign-off:** appeal states `draft → in_review → signed → exported`. Signing stores
   reviewer name, role, timestamp and SHA-256 of the exact content; edits after signing
   create a new version and require re-signing.

## 6. Frontend standards (enterprise, product-grade)

The bar: looks like a funded health-tech revenue-cycle product (claims ops / RCM tools),
designed by a senior product designer and built by a senior frontend engineer. Calm, dense,
trustworthy, fast. **Not** a generic AI-chat UI, not a gradient-heavy landing template.

- **Design tokens** live in `web/src/styles/tokens.css` (CSS variables) and the Tailwind
  theme maps to them. No raw hex values in components.
  - Brand: navy `#1E2A44` (primary text, primary buttons, nav), red-orange `#D9482B`
    (accent: "at risk" amounts, alerts, highlights, icons, large text only — it is ~4.3:1 on
    white), accent-strong `#B83B21` for small accent text and accent buttons with white
    labels (≥ 5:1), cream `#F7F2E8` (family surfaces, empty states, marketing), slate
    `#CDD3E0` (borders, dividers, muted fills).
  - App canvas for the desk is a very light neutral (`#F8F7F4`) with white cards; cream is
    reserved for the family experience so the two audiences feel distinct.
  - Semantic: success, warning (amber — also used for "Verify" citations), danger, info;
    each with bg/fg/border variants that pass WCAG AA.
- **Typography:** IBM Plex Sans (UI), IBM Plex Sans Devanagari (Hindi), Noto Sans Gujarati
  (Gujarati), IBM Plex Mono for IDs. All money and numbers use `font-variant-numeric:
  tabular-nums` and right alignment in tables. Self-host fonts (no third-party CDN calls).
- **Layout:** left sidebar app shell (collapsible), top bar with hospital switcher, global
  search (⌘K command palette), user menu. 8-pt spacing grid. Desk optimised for 1366–1920 px;
  family view mobile-first (360–430 px).
- **Every data view has all states:** skeleton loading, empty (illustrative + CTA), error
  (problem detail + retry + request ID), partial/low-confidence, success. No spinners on
  blank pages.
- **Interaction quality:** optimistic updates where safe, toasts for async results, inline
  validation, keyboard shortcuts on the claim workspace (`J/K` flags, `E` edit, `S` sign),
  focus management in dialogs, no layout shift, streaming progress for the audit pipeline.
- **Accessibility:** WCAG 2.1 AA. Every interactive element reachable by keyboard with a
  visible focus ring; labels on all inputs; `aria-live` for pipeline progress; colour never
  the only signal (icons + text on statuses). Playwright runs axe on key pages; zero
  serious/critical violations.
- **Copy:** plain, specific, non-hyped. Insurance jargon only on the desk side, and always
  with a tooltip definition. Family copy in spoken Gujarati/Hindi/English. Persistent
  footer note on claim pages: "Arzi is decision support. A qualified person reviews and signs
  every appeal."
- **Code:** feature folders (`features/claims`, `features/appeal`, `features/family`,
  `features/analytics`), server state only in TanStack Query, no global state library unless
  justified in an ADR, components < 200 lines, no `any`, no inline styles, `React.lazy` route
  splitting, images/fonts optimised. Lighthouse (desktop) ≥ 90 performance and accessibility
  on the worklist and claim pages.

## 7. Cost and cloud rules

- Region `asia-south1` for Cloud Run, Firestore, GCS, Artifact Registry. Gemini via Vertex AI
  in `asia-south1` if the chosen model is served there; otherwise the `global` endpoint, and
  record that in `docs/architecture.md` (data at rest remains in Mumbai).
- Cloud Run: `--min-instances=0 --max-instances=3 --cpu=1 --memory=1Gi --concurrency=20
  --timeout=300`. Bump `min-instances=1` **only** for the pitch window, then revert.
- Default model is the newest **Flash** tier; **Pro** only where an eval shows Flash is not
  good enough (record in PROGRESS). Low thinking budget for extraction.
- Do **not** provision Vertex AI Agent Engine, Vertex AI Search, GPUs, Memorystore, Cloud SQL,
  load balancers, NAT or always-on instances for the event build. They are roadmap items in
  `docs/architecture.md`, stated honestly as roadmap.
- **Budget guard:** `services/cost_ledger.py` estimates ₹ cost per LLM/TTS call from token
  usage × a price table in config (`ARZI_PRICE_TABLE_JSON`, values to be verified against the
  current Google pricing page). Daily cap `ARZI_DAILY_BUDGET_INR` (default 150). Over cap →
  live LLM calls refused with a clear problem response and the UI offers replay mode.
- GCS lifecycle deletes uploads after 30 days; Artifact Registry keeps the last 3 images.
- Never run load tests against the cloud deployment.

## 8. Testing standards

- **Rules engine:** 100% line + branch coverage. Worked example (case A) is a golden test.
  Hypothesis properties: ICU/pharmacy/diagnostics/implants never prorated; at-risk ≤ billed;
  payable + at-risk = billed; monotonicity (higher room rate never lowers at-risk); no
  negative amounts.
- **Backend overall:** ≥ 85% coverage. Unit tests use fakes; integration tests hit the
  FastAPI app via `httpx.AsyncClient` with fakes/replay. Tests never call real Google APIs
  unless marked `@pytest.mark.live` (excluded by default).
- **Guardrail tests:** citation whitelist rejects unknown refs; amount guard rejects stray
  rupee figures in en/hi/gu; redaction removes every identifier pattern in fixtures.
- **Frontend:** Vitest + Testing Library for components with logic (formatters, tables,
  appeal editor, sign gate). Playwright e2e for the three demo journeys in replay mode, with
  axe checks.
- **Evals:** `make eval` runs extraction field accuracy and flag precision/recall over the
  demo cases and writes `evals/report.md`. Numbers from this report feed the pitch.

## 9. Make targets (keep these working)

```
make setup        # uv sync, npm ci, git config core.hooksPath .githooks
make dev          # api (uvicorn --reload) + web (vite) with LLM_MODE=replay
make check        # ruff, mypy, eslint, tsc, pytest+coverage, vitest
make test-e2e     # playwright against local build in replay mode
make eval         # evals/report.md
make models       # list Gemini models available to the project
make demo-cases   # regenerate synthetic PDFs + expected.json
make openapi      # regenerate web/src/api/schema.d.ts
make deploy       # infra/deploy.sh (asks for confirmation; prints estimated cost note)
```

## 10. Definition of done (every task)

Code + tests + types + docs updated · `make check` green · no new warnings · no PII in logs ·
UI states complete · accessible · copy reviewed · committed with a Conventional Commit
message and **no attribution trailer**.
