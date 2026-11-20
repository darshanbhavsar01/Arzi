# 0005 — Citation whitelist and amount guard on all generated prose

- **Status:** accepted
- **Date:** 2026-11-20

## Context

Arzi's reasoning agents write explanations and appeal arguments that a hospital may send to an
insurer, a regulator's portal or the Ombudsman. Two failure modes would be unacceptable: a
made-up rupee figure (AGENTS.md §0.3: every amount comes from the rules engine) and a made-up
regulation (§0.4: never invent a circular, paragraph or clause). Prompting alone does not prevent
either.

## Decision

- **Placeholders, not figures.** Prose names amounts as `{{flag.<FLAG_ID>.amount|recoverable|
  fix_savings}}`, `{{totals.*}}`, `{{policy.*}}`, `{{letter.*}}` or `{{forum.ombudsman_limit}}`.
  The server renders them `en-IN` from engine output; Hindi and Gujarati keep Latin digits unless
  native digits are asked for. Prose is stored as `Prose{template, text}`, so a later line
  correction re-renders without another model call.
- **Amount guard.** Text (with placeholders removed) is rejected if it contains a written rupee
  figure: ₹, Rs., INR, rupees, रुपये/रु., રૂપિયા/રૂ., "/-", lakh/crore with digits, or a
  comma-grouped figure; Latin, Devanagari or Gujarati digits. A currency sign before a placeholder
  is rejected too (it would render twice).
- **Citation whitelist.** Each agent gets `allowed_refs`: registry IDs cited by the claim's flags
  or the forum, plus `policy:<clause>` for clauses in the redacted policy. Output `citations` must
  be a subset, and prose may not name an IRDAI circular code, "circular no.", clause or paragraph
  that is not in context.
- **On failure** the step is retried once with the validator's feedback (codes and fields only);
  a second failure keeps the draft as `needs_review`, with unrenderable text hidden behind a
  warning. Person-written appeal edits face the same checks and are rejected with a 422.
- Violations are stored and logged as `code in field`, never with the offending text.

## Consequences

- No generated amount or reference can reach a signed letter unchecked.
- The guard is conservative: a legitimate comma-grouped number in prose (rare in explanations)
  fails and must be rephrased. Percentages, months, days, dates and clause numbers pass.
- Citations with status `verify` are still allowed; the UI shows their amber badge.
