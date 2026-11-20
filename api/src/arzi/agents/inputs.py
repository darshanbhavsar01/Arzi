"""Inputs for the reasoning agents, built from redacted facts and engine output only.

They deliberately leave out anything that varies between runs of the same documents (claim IDs,
timestamps, pseudonyms, which depend on the deployment's key), so a recorded response replays
for every run of a demo case. Amounts never appear: agents get placeholder names instead.
"""

from collections.abc import Iterable
from typing import Any

from arzi.domain.models import AuditResult, ClaimFacts, Flag
from arzi.rules.context import POLICY_REF_PREFIX
from arzi.rules.reference import citations
from arzi.services.pipeline import RunContext

_CLAUSE_TEXT_MAX = 1500


def reconciled_facts(ctx: RunContext) -> ClaimFacts:
    if ctx.reconciled is None:  # pragma: no cover - the workflow orders the nodes
        raise RuntimeError("reasoning before reconcile")
    return ctx.reconciled.facts


def audited(ctx: RunContext) -> AuditResult:
    if ctx.audit is None:  # pragma: no cover - the workflow orders the nodes
        raise RuntimeError("explaining before the audit")
    return ctx.audit


def references(refs: Iterable[str], facts: ClaimFacts) -> list[dict[str, Any]]:
    """What each allowed ref says: the registry summary, or the policy clause's own text."""
    registry = citations()
    clauses = {c.id: c for c in facts.policy.clauses}
    out: list[dict[str, Any]] = []
    for ref in sorted(set(refs)):
        if ref in registry:
            entry = registry[ref]
            out.append(
                {
                    "id": ref,
                    "title": entry.title,
                    "reference": entry.ref,
                    "summary": entry.summary_en,
                    "status": str(entry.status),
                }
            )
            continue
        clause = clauses.get(ref.removeprefix(POLICY_REF_PREFIX))
        out.append(
            {
                "id": ref,
                "title": clause.title if clause else "Policy clause",
                "text": clause.text[:_CLAUSE_TEXT_MAX] if clause else "",
            }
        )
    return out


def flag_entry(flag: Flag, facts: ClaimFacts) -> dict[str, Any]:
    lines = {line.line_id: line for line in facts.bill_lines}
    return {
        "flag_id": flag.flag_id,
        "rule_id": flag.rule_id,
        "kind": str(flag.kind),
        "severity": str(flag.severity),
        "fix_code": str(flag.fix_code) if flag.fix_code else None,
        "appealable": flag.appealable,
        "missing_document": str(flag.missing_document) if flag.missing_document else None,
        "lines": [
            {
                "line_id": i,
                "description": lines[i].description,
                "category": str(lines[i].category),
                "irdai_list": str(lines[i].irdai_list) if lines[i].irdai_list else None,
            }
            for i in flag.lines
            if i in lines
        ],
        "citations": list(flag.citation_refs),
        "placeholders": [
            f"flag.{flag.flag_id}.amount",
            f"flag.{flag.flag_id}.recoverable",
            f"flag.{flag.flag_id}.fix_savings",
        ],
    }


def claim_context(facts: ClaimFacts) -> dict[str, Any]:
    """Non-monetary facts an explanation may need: dates, diagnosis, cover months, waiting
    periods, co-pay percentage and the insurer's stated grounds."""
    policy, admission, letter = facts.policy, facts.admission, facts.insurer_letter
    return {
        "mode": str(facts.mode),
        "insurer": policy.insurer,
        "admission": {
            "date_in": admission.date_in.isoformat() if admission.date_in else None,
            "date_out": admission.date_out.isoformat() if admission.date_out else None,
            "diagnosis": admission.diagnosis,
            "procedure": admission.procedure,
            "room_category_used": admission.room_category_used,
        },
        "policy": {
            "continuous_cover_months": policy.continuous_cover_months,
            "copay_percent": str(policy.copay.pct) if policy.copay else None,
            "ped_declared": [
                {
                    "condition": w.condition,
                    "waiting_months": w.waiting_months,
                    "clause": w.clause_id,
                }
                for w in policy.ped_declared
            ],
            "specific_waiting": [
                {
                    "condition": w.condition,
                    "waiting_months": w.waiting_months,
                    "clause": w.clause_id,
                }
                for w in policy.specific_waiting
            ],
        },
        "insurer_letter": None
        if letter is None
        else {
            "type": str(letter.type),
            "date": letter.date.isoformat() if letter.date else None,
            "rejection_ground": str(letter.rejection_ground) if letter.rejection_ground else None,
            "deduction_reasons": sorted({str(d.reason) for d in letter.deductions}),
        },
    }
