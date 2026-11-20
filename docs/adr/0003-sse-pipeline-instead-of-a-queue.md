# 0003 — Audit runs stream over SSE from the API instance, without a queue

- **Status:** accepted
- **Date:** 2026-11-20

## Context

An audit takes tens of seconds: several Gemini calls (one per document, a few at a time), then
redaction, reconciliation and the rules engine. The desk wants to watch it happen ("Reading the
bill… 4 flags found"). The usual design is a job queue (Cloud Tasks or Pub/Sub) plus workers plus
a push channel. That is more infrastructure, more IAM and more always-on cost than a ₹500 event
budget and a one-person team can carry. Cloud Run bills CPU only while a request is in flight.

## Decision

- `POST /claims/{cid}/runs` (with `Idempotency-Key`) creates the run and starts the pipeline as a
  task in the same instance. The browser then opens
  `GET /claims/{cid}/runs/{rid}/events`, a `text/event-stream` that stays open until the run ends,
  which keeps the instance's CPU allocated without min-instances.
- Every event is appended to the run document in Firestore *before* it is announced. The event
  `seq` is the SSE `id`, so a reconnecting browser sends `Last-Event-ID` and resumes. A subscriber
  on another instance follows the run by polling the run document once a second.
- The pipeline is a list of `PipelineStep`s (`extract → redact → reconcile → audit`) behind one
  event contract (`stage.started`, `stage.completed`, `flag.created`, `run.completed`,
  `run.failed`). Phase 4's agent steps plug into the same list.
- Failures end the run with a stable error slug (`replay-miss`, `budget-exceeded`,
  `facts-incomplete`), never an exception message.

## Consequences

- No queue, workers or extra IAM; scale-to-zero holds.
- If the instance dies mid-run, the run stays `running` until retried; the claim can be
  re-audited. Acceptable for decision support, and recorded as a follow-up: a stale-run sweeper,
  or Cloud Tasks if volumes grow.
- Long single runs are bounded by the Cloud Run request timeout (300 s), well above the expected
  audit time.
