# Architecture

Arzi is one Cloud Run service (`arzi`, `asia-south1`) that serves a FastAPI backend and the built
React app. State lives in Firestore and Cloud Storage in Mumbai; Gemini runs on Vertex AI.

```
 browser (desk SPA, family page, free check)
        │  HTTPS, JSON + SSE
        ▼
 Cloud Run: FastAPI ── api → services → (rules | agents | adapters)
        │                      │            │         │
        │                      │            │         ├─ Firestore (claims, runs, audit log, appeals)
        │                      │            │         ├─ Cloud Storage (uploads, narrated audio)
        │                      │            │         └─ Vertex AI: Gemini (extract, explain, draft, TTS)
        │                      │            └─ ADK workflow: extract → redact → reconcile →
        │                      │               policy interpreter → rules engine → flag explainer
        │                      └─ pure Python rules engine, integer paise, no I/O
```

Key decisions are in [`docs/adr/`](adr/): money as integer paise, an SSE pipeline instead of a
queue, ADK in process, citation whitelist plus amount guard, one container for API and SPA.

## Guardrails (product features)
- **Rupee maths is deterministic.** Every amount comes from `arzi.rules`; model text carries
  placeholders the server fills, and an amount guard rejects stray figures in en/hi/gu.
- **Citation whitelist.** Agents may cite only rule IDs and policy clauses in context; `verify`
  citations show an amber "Verify before filing" badge.
- **Redaction before reasoning**, **extraction confidence** ("Needs confirmation"), and
  **human sign-off**: an appeal is exportable only after a reviewer or admin signs the exact
  content (SHA-256 stored). The role is enforced by the API, not just the UI.

## Built vs roadmap

The event deployment ran on Cloud Run from 20 to 22 November 2026 and has been retired; every
screen is recorded in [`docs/screens/live/`](screens/live/README.md). "Built" means it is in this
repository, tested, and ran on that deployment unless the row says otherwise.

| Capability | Status |
|---|---|
| Gemini multimodal extraction, ADK multi-agent pipeline on Vertex AI | **Built** (deployment ran hybrid: recorded responses for demo cases, live otherwise) |
| Deterministic rules engine, citation and amount guardrails | **Built** |
| Appeals with forum checklist, reviewer sign-off, signed PDF | **Built** |
| Family page in English, Hindi, Gujarati with Gemini TTS narration | **Built** |
| Free rejection check at `/check` | **Built** |
| Desk analytics (insurer, stage, week, recovery funnel) | **Built** (computed from the worklist) |
| Firestore + Cloud Storage in Mumbai, Cloud Run, per-day budget guard, cost ledger | **Built** |
| Demo-workspace sign-in; reviewer-only signing and export | **Built** |
| Per-rule ₹ chart, BigQuery export, Looker Studio | Roadmap |
| Firebase Auth (SSO), per-tenant role admin | Roadmap |
| Tenancy sweep (every claim route as another hospital → 404), role tests | **Built** (after the event) |
| CSP, HSTS, no-referrer, frame-ancestors none, request cap, per-client rate limit, active-PDF refusal | **Built** (after the event) |
| DPDP export and erasure, retention sweep, PII-scrubbing JSON logs with trace correlation, `/meta/status` | **Built** (after the event); see [`privacy.md`](privacy.md) |
| Dependency audit (pip-audit, npm audit) in CI | **Built** |
| OpenTelemetry spans exported to Cloud Trace | Roadmap (logs already carry the Cloud Trace ID) |
| Sensitive Data Protection and Document AI fallbacks | Roadmap |
| Gemini Live Q&A on the family page | Roadmap |
| Gemma redaction inside the hospital's project, Vertex AI Search over circulars, Agent Engine, VPC-SC | Roadmap |
| NHCX (FHIR) and WhatsApp intake, Terraform onboarding | Roadmap |

### LLM modes
`replay` serves the three demo cases from Gemini responses recorded on the project's models
(instant, free, reliable on venue Wi-Fi); any other document returns `replay-miss`. `hybrid`, which
the event deployment ran, serves recordings when they exist and calls Vertex AI behind the daily
budget guard (`ARZI_DAILY_BUDGET_INR`) otherwise. `live` calls Vertex AI for everything.

### Vertex AI location
Models are served from the `global` endpoint (`ARZI_VERTEX_LOCATION=global`); data at rest stays
in Mumbai.

## Evaluation
`make eval` replays the demo cases and writes [`evals/report.md`](../evals/report.md): 11/11
flags caught, 11/11 exact rupee amounts, totals exact on all cases, median 0.23 s (replay).
