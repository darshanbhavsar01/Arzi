"""PolicyInterpreter: which clause of the redacted policy governs each term the engine reads.

It does not change the facts the engine runs on (extraction and reconciliation own those). It
is a second, independent reading: a term whose clause disagrees with the one extraction used,
or that the model is unsure about, becomes a "Needs confirmation" issue for the desk, and its
plain-language summaries ground the flag explanations and appeals.
"""

from collections.abc import Sequence
from typing import Any

from arzi.agents.guardrails import (
    ProsePolicy,
    Violation,
    allowed_refs,
    check_prose,
    placeholder_values,
    policy_clause_ids,
    try_render,
    validate_citations,
)
from arzi.agents.inputs import reconciled_facts, references
from arzi.agents.nodes import ReasoningTask
from arzi.agents.schemas import PolicyTermsDraft
from arzi.domain.enums import PolicyTermKind, ReasoningStatus
from arzi.domain.models import Policy, PolicyReview, PolicyTermNote, Prose, ReviewIssue
from arzi.prompts import load_prompt
from arzi.services.pipeline import RunContext, Summary

PROMPT = load_prompt("interpret_policy", 1)
NAME = "interpret_policy"
CONFIDENCE_FLOOR = 0.8
_LABELS = {
    PolicyTermKind.ROOM_RENT_CAP: "the room-rent cap",
    PolicyTermKind.PROPORTIONATE_DEDUCTION: "proportionate deduction",
    PolicyTermKind.ICU_CAP: "the ICU cap",
    PolicyTermKind.COPAY: "co-payment",
    PolicyTermKind.SUB_LIMIT: "sub-limits",
    PolicyTermKind.PED_WAITING: "the pre-existing disease waiting period",
    PolicyTermKind.SPECIFIC_WAITING: "specific waiting periods",
    PolicyTermKind.ASSOCIATED_EXPENSES: "associated medical expenses",
    PolicyTermKind.NON_PAYABLE_COVER: "cover for non-payable items",
    PolicyTermKind.CLAIM_DOCUMENTS: "claim documents",
}


def extracted_clauses(policy: Policy) -> dict[PolicyTermKind, frozenset[str]]:
    """The clause(s) extraction tied to each term, to compare the interpreter's reading with."""
    k = PolicyTermKind
    single = {
        k.ROOM_RENT_CAP: policy.room_rent_cap.clause_id if policy.room_rent_cap else None,
        k.PROPORTIONATE_DEDUCTION: policy.proportionate_clause_id,
        k.ICU_CAP: policy.icu_cap.clause_id if policy.icu_cap else None,
        k.COPAY: policy.copay.clause_id if policy.copay else None,
        k.CLAIM_DOCUMENTS: policy.claims_clause_id,
    }
    found = {term: frozenset({c}) for term, c in single.items() if c}
    groups = {
        k.PED_WAITING: [w.clause_id for w in policy.ped_declared],
        k.SPECIFIC_WAITING: [w.clause_id for w in policy.specific_waiting],
        k.SUB_LIMIT: [s.clause_id for s in policy.sub_limits],
    }
    for term, cited in groups.items():
        ids = frozenset(c for c in cited if c)
        if ids:
            found[term] = ids
    return found


def task(ctx: RunContext) -> ReasoningTask[PolicyTermsDraft]:
    def prose_policy() -> ProsePolicy:
        facts = reconciled_facts(ctx)
        return ProsePolicy(allowed_refs(facts), frozenset(placeholder_values(facts)))

    def build() -> dict[str, Any] | None:
        facts = ctx.reconciled.facts if ctx.reconciled else None
        if facts is None or not policy_clause_ids(facts.policy):
            return None
        policy = prose_policy()
        return {
            "insurer": facts.policy.insurer,
            "terms_to_map": [str(t) for t in PolicyTermKind],
            "extracted": {
                str(t): sorted(ids) for t, ids in extracted_clauses(facts.policy).items()
            },
            "clauses": references(policy.allowed_refs, facts),
            "allowed_refs": sorted(policy.allowed_refs),
            "placeholders": sorted(policy.placeholders),
        }

    def check(output: PolicyTermsDraft) -> Sequence[Violation]:
        policy = prose_policy()
        found = validate_citations(output.citations, policy.allowed_refs, "citations")
        for i, term in enumerate(output.terms):
            where = f"terms[{i}]"
            if term.clause_id and term.clause_id not in policy.clause_ids:
                found.append(Violation("unknown_clause", f"{where}.clause_id"))
            found += check_prose(term.summary, policy, f"{where}.summary")
        return found

    def finish(
        output: PolicyTermsDraft | None, status: ReasoningStatus, violations: Sequence[Violation]
    ) -> Summary:
        notes: list[PolicyTermNote] = []
        if output is not None:
            facts = reconciled_facts(ctx)
            values = placeholder_values(facts)
            extracted = extracted_clauses(facts.policy)
            for term in output.terms:
                used = extracted.get(term.term, frozenset())
                disagrees = bool(term.clause_id and used and term.clause_id not in used)
                unsure = (
                    term.confidence < CONFIDENCE_FLOOR or status is ReasoningStatus.NEEDS_REVIEW
                )
                notes.append(
                    PolicyTermNote(
                        term=term.term,
                        clause_id=term.clause_id,
                        summary=Prose(template=term.summary, text=try_render(term.summary, values)),
                        confidence=term.confidence,
                        needs_confirmation=disagrees or unsure,
                    )
                )
                if disagrees:
                    ctx.review_issues.append(
                        ReviewIssue(
                            code="policy_term_unconfirmed",
                            message=f"Confirm the clause for {_LABELS[term.term]}: the policy "
                            f"reading points to clause {term.clause_id}, extraction used "
                            f"{', '.join(sorted(used))}.",
                        )
                    )
        ctx.policy_review = PolicyReview(
            status=status,
            prompt_ref=PROMPT.ref if status is not ReasoningStatus.SKIPPED else None,
            violations=tuple(str(v) for v in violations),
            terms=tuple(notes),
        )
        return {
            "status": str(status),
            "terms": len(notes),
            "needs_confirmation": sum(n.needs_confirmation for n in notes),
        }

    return ReasoningTask(
        name=NAME,
        prompt=PROMPT,
        schema=PolicyTermsDraft,
        build_input=build,
        check=check,
        finish=finish,
        max_output_tokens=8192,
    )
