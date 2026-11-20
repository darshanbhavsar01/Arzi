"""FlagExplainer: a plain-language explanation and next step for every engine flag.

The engine decides what is flagged and for how much; this agent only says why, in words a
billing executive can act on. Each explanation must cover exactly the engine's flags, cite only
refs in context, and mention money only through the flag's placeholders.
"""

from collections.abc import Sequence
from typing import Any

from arzi.agents.guardrails import (
    ProsePolicy,
    Violation,
    allowed_refs,
    check_prose,
    placeholder_values,
    try_render,
    validate_citations,
)
from arzi.agents.inputs import audited, claim_context, flag_entry, reconciled_facts, references
from arzi.agents.nodes import ReasoningTask
from arzi.agents.schemas import FlagNarrativesDraft
from arzi.domain.enums import ReasoningStatus
from arzi.domain.models import ClaimNarratives, FlagNarrative, Prose
from arzi.prompts import load_prompt
from arzi.services.pipeline import RunContext, Summary

PROMPT = load_prompt("explain_flags", 1)
NAME = "explain_flags"


def check_coverage(written: Sequence[str], expected: Sequence[str]) -> list[Violation]:
    """Exactly one entry per expected flag: none missing, none invented."""
    found: list[Violation] = []
    if set(expected) - set(written):
        found.append(Violation("missing_flag", "items"))
    if set(written) - set(expected) or len(written) != len(set(written)):
        found.append(Violation("unexpected_flag", "items"))
    return found


def task(ctx: RunContext) -> ReasoningTask[FlagNarrativesDraft]:
    def prose_policy() -> ProsePolicy:
        facts, result = reconciled_facts(ctx), audited(ctx)
        refs = allowed_refs(facts, (r for f in result.flags for r in f.citation_refs))
        return ProsePolicy(refs, frozenset(placeholder_values(facts, result)))

    def build() -> dict[str, Any] | None:
        if ctx.audit is None or not ctx.audit.flags:
            return None
        facts, policy = reconciled_facts(ctx), prose_policy()
        return {
            "claim": claim_context(facts),
            "flags": [flag_entry(flag, facts) for flag in ctx.audit.flags],
            "references": references(policy.allowed_refs, facts),
            "allowed_refs": sorted(policy.allowed_refs),
            "placeholders": sorted(policy.placeholders),
        }

    def check(output: FlagNarrativesDraft) -> Sequence[Violation]:
        policy = prose_policy()
        found = check_coverage(
            [i.flag_id for i in output.items], [f.flag_id for f in audited(ctx).flags]
        )
        for i, item in enumerate(output.items):
            where = f"items[{i}]"
            found += validate_citations(item.citations, policy.allowed_refs, f"{where}.citations")
            for field in ("headline", "explanation", "fix"):
                found += check_prose(getattr(item, field), policy, f"{where}.{field}")
        return found

    def finish(
        output: FlagNarrativesDraft | None, status: ReasoningStatus, violations: Sequence[Violation]
    ) -> Summary:
        items: list[FlagNarrative] = []
        if output is not None:
            values = placeholder_values(reconciled_facts(ctx), audited(ctx))

            def prose(template: str) -> Prose:
                return Prose(template=template, text=try_render(template, values))

            items = [
                FlagNarrative(
                    flag_id=item.flag_id,
                    headline=prose(item.headline),
                    explanation=prose(item.explanation),
                    fix=prose(item.fix),
                    citations=tuple(item.citations),
                )
                for item in output.items
            ]
        ctx.narratives = ClaimNarratives(
            status=status,
            prompt_ref=PROMPT.ref if status is not ReasoningStatus.SKIPPED else None,
            violations=tuple(str(v) for v in violations),
            items=tuple(items),
        )
        return {"status": str(status), "explained": len(items), "violations": len(violations)}

    return ReasoningTask(
        name=NAME,
        prompt=PROMPT,
        schema=FlagNarrativesDraft,
        build_input=build,
        check=check,
        finish=finish,
        max_output_tokens=8192,
    )
