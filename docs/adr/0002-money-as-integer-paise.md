# 0002 — Money as integer paise, computed only by the rules engine

- **Status:** accepted
- **Date:** 2026-11-20

## Context

Every rupee figure Arzi produces ends up in front of a billing desk, an insurer or an
Ombudsman: "₹67,887.50 at risk", "₹20,137.50 recoverable". A figure that is off by a paisa
between the screen, the PDF and the spoken explanation destroys trust in the whole audit.
Binary floats cannot represent most rupee-and-paise amounts exactly, and an LLM asked to do
arithmetic is not reproducible at all.

## Decision

- Amounts are `Paise = NewType("Paise", int)` everywhere: domain models, Firestore, the API.
  Extracted text is parsed once at the boundary (`to_paise`, via `Decimal`); floats and
  booleans are rejected outright.
- All scaling (ratios, percentages, fractional days) goes through `Decimal` or exact
  `Fraction` arithmetic with `ROUND_HALF_UP` to the paisa. A claim-level result split across
  lines uses largest-remainder allocation, so the parts always sum to the whole.
- Formatting (`₹1,57,612.50`, en-IN grouping) happens only at presentation time.
- Only `arzi.rules.engine.audit` computes money. It is pure (no I/O, no model calls), and an
  architecture test fails the build if `rules/` or `domain/` imports an I/O layer or SDK.
  LLM output may reference amounts only through placeholders that the server fills from the
  engine result (amount guard, Phase 4).
- Each computation is recorded as a human-readable trace step
  (`₹93,000 associated expenses × ₹5,000 / ₹8,000 = ₹58,125`) that flags point to.

## Consequences

- The golden cases are exact-equality tests, and Hypothesis properties
  (`payable + at_risk = billed`, never negative, monotone in room rate) hold to the paisa.
- API clients receive integers in paise and must format them; the generated TypeScript client
  documents this, and the web app gets one shared formatter.
- Rupee units for external systems (e.g. NHCX) need an explicit conversion at that boundary.
