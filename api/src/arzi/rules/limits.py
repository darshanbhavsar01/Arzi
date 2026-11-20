"""Policy limits: procedure sub-limits and co-pay.

Sub-limits run after the room-rent rules: a sub-limit caps what is otherwise admissible, so
applying it first and prorating afterwards would cut the same rupee twice.
"""

from arzi.domain.enums import CopayBase, FixCode, FlagKind, Severity
from arzi.domain.models import ClaimFacts, Flag
from arzi.domain.money import Paise, allocate, format_inr, percent_of, total
from arzi.rules.context import AuditContext, fmt_qty, line_ids, policy_refs
from arzi.rules.matching import mentions

SUB_LIMIT = "SUB_LIMIT"
COPAY = "COPAY"


def sub_limit(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """Each sub-limit naming this admission's procedure or diagnosis caps its scoped lines."""
    flags = []
    admission = (facts.admission.procedure, facts.admission.diagnosis)
    for number, limit in enumerate(facts.policy.sub_limits, start=1):
        if not mentions(limit.item, admission):
            continue
        lines = ctx.open_lines(limit.categories or None)
        weights = [ctx.remaining[line.line_id] for line in lines]
        excess = Paise(total(weights) - limit.limit)
        if excess <= 0:
            continue
        for line, part in zip(lines, allocate(excess, weights), strict=True):
            ctx.cut(line, SUB_LIMIT, part)
        step_id = ctx.step(
            SUB_LIMIT,
            f"{format_inr(total(weights))} admissible for '{limit.item}' - "
            f"{format_inr(limit.limit)} sub-limit = {format_inr(excess)}",
            result=excess,
            inputs={"item": limit.item, "limit": limit.limit},
        )
        flags.append(
            Flag(
                flag_id=f"{SUB_LIMIT}-{number}",
                rule_id=SUB_LIMIT,
                kind=FlagKind.DEDUCTION,
                severity=Severity.MEDIUM,
                amount_at_risk=excess,
                lines=line_ids(lines),
                citation_refs=policy_refs([limit.clause_id]),
                fix_code=FixCode.INFORM_PATIENT,
                trace_ref=step_id,
            )
        )
    return flags


def copay(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """Co-pay % of the base the policy names (admissible by default), never above payable."""
    policy_copay = facts.policy.copay
    if policy_copay is None:
        return []
    claimed = policy_copay.base is CopayBase.CLAIMED
    base = ctx.billed if claimed else ctx.lines_admissible
    amount = min(percent_of(base, policy_copay.pct), ctx.payable)
    if amount == 0:
        return []
    ctx.cut_claim(COPAY, amount)
    step_id = ctx.step(
        COPAY,
        f"{fmt_qty(policy_copay.pct)}% × {format_inr(base)} "
        f"{'claimed' if claimed else 'admissible'} = {format_inr(amount)} co-pay",
        result=amount,
        inputs={"pct": fmt_qty(policy_copay.pct), "base": base},
    )
    return [
        Flag(
            flag_id=COPAY,
            rule_id=COPAY,
            kind=FlagKind.DEDUCTION,
            severity=Severity.INFO,
            amount_at_risk=amount,
            lines=line_ids(ctx.open_lines()),
            citation_refs=policy_refs([policy_copay.clause_id]),
            fix_code=FixCode.INFORM_PATIENT,
            trace_ref=step_id,
        )
    ]
