"""AppealDrafter: the arguments of a forum-specific appeal, around engine-owned facts.

What is disputed, for how much, the insurer's stated reason, the relief total and the citations
behind each item all come from the rules engine and the letter. The agent writes the subject,
a short statement of facts, the argument for each disputed item and the relief sentence, with
money only as placeholders and refs only from ``allowed_refs``.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from arzi.agents.flag_explainer import check_coverage
from arzi.agents.guardrails import (
    ProsePolicy,
    Violation,
    allowed_refs,
    check_prose,
    placeholder_values,
    validate_citations,
)
from arzi.agents.inputs import claim_context, flag_entry, references
from arzi.agents.nodes import ReasoningTask
from arzi.agents.schemas import AppealDraftOutput
from arzi.domain.enums import AppealForum, FlagKind, ReasoningStatus, RejectionGround
from arzi.domain.models import AuditResult, ClaimFacts, Flag
from arzi.prompts import Prompt, load_prompt
from arzi.rules.disputes import PROP_WRONGLY_APPLIED
from arzi.rules.non_payable import SUBSUMED_ITEM
from arzi.rules.waiting import MORATORIUM, WAITING_REJECTION_INVALID
from arzi.services.pipeline import Summary

RELIEF_PLACEHOLDER = "totals.recoverable"
PROMPTS: dict[AppealForum, Prompt] = {
    forum: load_prompt(f"appeal_{forum}", 1) for forum in AppealForum
}
FORUM_REFS: dict[AppealForum, tuple[str, ...]] = {
    AppealForum.INSURER_GRO: ("INSURER_GRIEVANCE_15D",),
    AppealForum.BIMA_BHAROSA: ("BIMA_BHAROSA",),
    AppealForum.OMBUDSMAN: ("OMBUDSMAN_RULES_2017",),
}
_GROUND = {
    RejectionGround.PED_WAITING: "Rejected under the pre-existing disease waiting period",
    RejectionGround.SPECIFIC_WAITING: "Rejected under a specific-disease waiting period",
    RejectionGround.NON_DISCLOSURE: "Rejected for non-disclosure",
}


def disputed(result: AuditResult) -> list[Flag]:
    """The flags an appeal argues: insurer decisions the engine found wrong."""
    return [f for f in result.flags if f.kind is FlagKind.DISPUTE and f.appealable]


def insurer_reason(flag: Flag, facts: ClaimFacts) -> str:
    """The insurer's position on a disputed item, in fixed words (its letter's own text can
    quote amounts, which only the engine may state)."""
    if flag.rule_id == PROP_WRONGLY_APPLIED:
        return "Proportionate deduction applied for the room category"
    if flag.rule_id == SUBSUMED_ITEM:
        return "Deducted as a non-payable item"
    letter = facts.insurer_letter
    ground = letter.rejection_ground if letter else None
    if flag.rule_id in {WAITING_REJECTION_INVALID, MORATORIUM} and ground in _GROUND:
        return _GROUND[ground]
    return "As stated in the insurer's letter"


@dataclass
class AppealJob:
    """One drafting request; ``finish`` stores the outcome here."""

    facts: ClaimFacts
    audit: AuditResult
    forum: AppealForum
    output: AppealDraftOutput | None = None
    status: ReasoningStatus = ReasoningStatus.UNAVAILABLE
    violations: tuple[Violation, ...] = field(default_factory=tuple)

    @property
    def prompt(self) -> Prompt:
        return PROMPTS[self.forum]

    def prose_policy(self) -> ProsePolicy:
        cited = [r for f in disputed(self.audit) for r in f.citation_refs]
        refs = allowed_refs(self.facts, (*cited, *FORUM_REFS[self.forum]))
        return ProsePolicy(refs, frozenset(placeholder_values(self.facts, self.audit)))


def task(job: AppealJob) -> ReasoningTask[AppealDraftOutput]:
    def build() -> dict[str, Any] | None:
        items = disputed(job.audit)
        if not items:
            return None
        policy = job.prose_policy()
        return {
            "forum": str(job.forum),
            "claim": claim_context(job.facts),
            "disputed": [
                flag_entry(flag, job.facts)
                | {
                    "insurer_reason": insurer_reason(flag, job.facts),
                    "amount_placeholder": f"flag.{flag.flag_id}.recoverable",
                }
                for flag in items
            ],
            "relief_placeholder": RELIEF_PLACEHOLDER,
            "references": references(policy.allowed_refs, job.facts),
            "allowed_refs": sorted(policy.allowed_refs),
            "placeholders": sorted(policy.placeholders),
        }

    def check(output: AppealDraftOutput) -> Sequence[Violation]:
        policy = job.prose_policy()
        found = check_coverage(
            [i.flag_id for i in output.items], [f.flag_id for f in disputed(job.audit)]
        )
        found += validate_citations(output.citations, policy.allowed_refs, "citations")
        for name in ("subject", "facts", "relief"):
            found += check_prose(getattr(output, name), policy, name)
        if "{{" + RELIEF_PLACEHOLDER + "}}" not in output.relief.replace(" ", ""):
            found.append(Violation("missing_relief", "relief"))
        for i, item in enumerate(output.items):
            where = f"items[{i}]"
            found += validate_citations(item.citations, policy.allowed_refs, f"{where}.citations")
            found += check_prose(item.argument, policy, f"{where}.argument")
        return found

    def finish(
        output: AppealDraftOutput | None, status: ReasoningStatus, violations: Sequence[Violation]
    ) -> Summary:
        job.output, job.status, job.violations = output, status, tuple(violations)
        return {"status": str(status), "violations": len(violations)}

    return ReasoningTask(
        name="draft_appeal",
        prompt=job.prompt,
        schema=AppealDraftOutput,
        build_input=build,
        check=check,
        finish=finish,
        max_output_tokens=8192,
    )
