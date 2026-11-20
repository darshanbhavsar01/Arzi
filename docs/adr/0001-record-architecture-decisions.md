# 0001 — Record architecture decisions

- **Status:** accepted
- **Date:** 2026-11-20

## Context

Arzi is built fast, by a very small team, and will be reviewed by judges, future engineers and
eventually hospital IT and compliance teams. Decisions such as "money is integer paise" or "the
LLM never computes rupees" look arbitrary in code unless the reasoning is written down next to
it. Chat history and commit messages are not a reliable place for that reasoning.

## Decision

Record each significant architectural decision as a short Architecture Decision Record in
`docs/adr/NNNN-kebab-title.md`, numbered sequentially, with the sections **Context →
Decision → Consequences** and a status (`proposed`, `accepted`, `superseded by NNNN`).

- An ADR is written in the same change that implements the decision.
- ADRs are immutable once accepted; a change of mind is a new ADR that supersedes the old one.
- `docs/PROGRESS.md` "Decisions" links to the ADR when one exists.

ADRs already expected (from `AGENTS.md`): money as paise; SSE pipeline instead of a queue; ADK
in-process on Cloud Run; citation whitelist + amount guard; single container serving API + SPA.

## Consequences

- Reviewers can trace why the system looks the way it does without reading the whole history.
- A small, ongoing writing cost per decision, kept low by the one-page format.
- Smaller decisions that do not warrant an ADR are logged as one line in `docs/PROGRESS.md`.
