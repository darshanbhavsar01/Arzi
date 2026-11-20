# Arzi

**Your claim, defended before and after the insurer says no.** Arzi audits Indian hospital
health-insurance claims before filing, shows every likely deduction with the ₹ at risk and the
exact policy clause or IRDAI rule, and drafts clause-cited appeals that a qualified person
reviews and signs.

> Arzi is decision support. A qualified person reviews and signs every appeal.
> All data in this repository is synthetic; hospitals and insurers named in demos are fictional.

<!-- Screenshot: added in Phase 5 (docs/screens/) -->

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js ≥ 22, GNU Make and bash (Git Bash on
Windows). The Google Cloud SDK is needed only for cloud targets.

```bash
make setup   # Python + Node dependencies, enables the commit-msg hook
make dev     # API on :8000 and web on :5173, LLM calls served from recordings (replay mode)
make check   # lint, types, tests and coverage gates — the same checks CI runs
```

Run `make help` for every target.

## Architecture

FastAPI (Python 3.12) and a React + TypeScript single-page app, shipped as one container on
Cloud Run in `asia-south1` (Mumbai), with Firestore and Cloud Storage in the same region and
Gemini on Vertex AI. Rupee amounts come only from a deterministic rules engine; the model
extracts, explains, cites and drafts.

- Architecture and the **Live vs roadmap** table: [`docs/architecture.md`](docs/architecture.md) (Phase 9)
- Build plan and status: [`docs/BUILD_PLAN.md`](docs/BUILD_PLAN.md), [`docs/PROGRESS.md`](docs/PROGRESS.md)
- Decisions: [`docs/adr/`](docs/adr/)
- Operations, kill switches and billing: [`docs/runbook.md`](docs/runbook.md)

## Configuration

All settings are environment variables declared in
[`api/src/arzi/config.py`](api/src/arzi/config.py) (prefix `ARZI_`, plus `GOOGLE_CLOUD_PROJECT`).
Model IDs are configuration and are never hard-coded; `make models` lists what the project can use.

## Licence

To be decided. All rights reserved until a licence is added.
