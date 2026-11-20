# 0004 — The audit is an ADK Workflow, run in-process, with models behind Arzi's LLM port

- **Status:** accepted
- **Date:** 2026-11-20

## Context

Phase 4 makes Google ADK load-bearing: the audit becomes a multi-agent pipeline (document
extraction, redaction, policy interpretation, the rules engine, flag explanations), and appeal
drafting is an agent too. Three constraints shape how:

- Every model call must keep going through the existing `LlmClient` port: `replay` mode (the
  venue-Wi-Fi fallback and free tests), `fake` mode, the budget guard, the cost ledger, the
  timeout and retry policy, and prompt-version recording. ADK's `LlmAgent` would otherwise call
  Gemini itself and bypass all of it.
- The Phase 3 SSE contract (`stage.started`, `stage.completed`, `flag.created`, `run.completed`,
  `run.failed`) must not change, so the frontend is unaffected.
- No Vertex AI Agent Engine or other always-on infrastructure for the event build (AGENTS.md §7).

The installed `google-adk` is 2.15. It deprecates `SequentialAgent` in favour of `Workflow`
(a graph of nodes; agents are nodes). The newest ADK requires `google-genai` 2.x, so
`google-genai` moves from 3.6 to 2.34; the APIs Arzi uses (`Client`, `aio.models.generate_content`,
`GenerateContentConfig`, `ThinkingConfig`, `Part.from_uri/from_bytes`, `errors.APIError`) are the
same, and the whole suite passes on it.

## Decision

- The audit is `Workflow(START → extract → redact → reconcile → interpret_policy → audit →
  explain_flags)`, built fresh for each run, run by an ADK `Runner` with an `InMemorySessionService`
  inside the Cloud Run instance that accepted the run (ADR-0003).
- Deterministic steps are custom `BaseAgent`s wrapping the Phase 3 `PipelineStep`s. Reasoning
  steps are `LlmAgent(output_schema=…, include_contents="none")` wrapped in a guard agent that runs
  the guardrails (ADR-0005), retries once with the validator's feedback, then keeps the draft as
  `needs_review`. A model that is unavailable leaves the step `unavailable`; the deterministic
  audit still completes.
- `LlmAgent`s use `PortModel`, a `BaseLlm` that sends the versioned prompt plus the run's input
  (between `<arzi-input>` markers in the instruction) through the `LlmClient` port. Anything ADK
  appends to the instruction is not sent, so recordings stay keyed by prompt version and input.
- Nodes announce `stage.started`/`stage.completed` in `Event.custom_metadata`; the pipeline maps
  those 1:1 onto run events and announces `flag.created` as soon as the engine has run.
- Appeal drafting runs the same guarded node on its own (`run_reasoning`).
- Agent inputs contain only redacted facts and engine output, without claim IDs, timestamps or
  pseudonyms, so a recorded response replays for every run of a demo case.

## Consequences

- ADK orchestrates every stage, and replay, fake, budget and cost behave exactly as before.
- The ADK session is discarded after each run; the run document in Firestore stays the source of
  truth. A resumed or cross-instance subscriber is unaffected.
- `google-genai` is pinned below 3 until ADK supports it.
- Roadmap (not built): Vertex AI Agent Engine sessions and memory, and running the explainer in
  parallel with the engine.
