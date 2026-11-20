"""IRDAI Annexure I: List I items are not payable; Lists II-IV are part of another charge.

A human's confirmation of a line's list always wins over the matcher, including a human
saying "not on any list". Unconfirmed lines are classified only by the conservative matcher.
"""

from arzi.domain.enums import (
    ClaimMode,
    DeductionReason,
    FixCode,
    FlagKind,
    IrdaiList,
    Severity,
)
from arzi.domain.models import BillLine, ClaimFacts, Flag
from arzi.domain.money import Paise, format_inr, total
from arzi.rules.context import AuditContext, line_ids
from arzi.rules.matching import match_non_payable

NON_PAYABLE = "NON_PAYABLE"
SUBSUMED_ITEM = "SUBSUMED_ITEM"

CITATIONS = ("IRDAI_NON_PAYABLE_ANNEX_I",)
SUBSUMED_LISTS = frozenset({IrdaiList.II, IrdaiList.III, IrdaiList.IV})


def irdai_list(line: BillLine) -> IrdaiList | None:
    if line.confirmed_by_human:
        return line.irdai_list
    match = match_non_payable(line.description)
    return match.item.list if match else None


def _describe(lines: list[BillLine], ctx: AuditContext) -> str:
    parts = " + ".join(
        f"{line.description} {format_inr(ctx.remaining[line.line_id])}" for line in lines
    )
    return f"{parts} = {format_inr(total(ctx.remaining[line.line_id] for line in lines))}"


def non_payable(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """List I lines are cut in full unless the policy's add-on covers them."""
    lines = [line for line in ctx.open_lines() if irdai_list(line) is IrdaiList.I]
    if not lines:
        return []
    if facts.policy.non_payable_addon:
        ctx.step(NON_PAYABLE, f"{_describe(lines, ctx)} covered by the non-payable add-on")
        return []
    step_id = ctx.step(NON_PAYABLE, f"{_describe(lines, ctx)} not payable (IRDAI List I)")
    amount = total(ctx.remaining[line.line_id] for line in lines)
    for line in lines:
        ctx.cut(line, NON_PAYABLE, ctx.remaining[line.line_id])
    return [
        Flag(
            flag_id=NON_PAYABLE,
            rule_id=NON_PAYABLE,
            kind=FlagKind.DEDUCTION,
            severity=Severity.MEDIUM,
            amount_at_risk=amount,
            lines=line_ids(lines),
            citation_refs=CITATIONS,
            fix_code=FixCode.COLLECT_FROM_PATIENT,
            trace_ref=step_id,
        )
    ]


def subsumed_item(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """Lists II-IV: warn before filing; after a deduction, a separate cut is recoverable."""
    lines = [line for line in facts.bill_lines if irdai_list(line) in SUBSUMED_LISTS]
    if not lines:
        return []
    if facts.mode is ClaimMode.PRE_SUBMISSION:
        step_id = ctx.step(
            SUBSUMED_ITEM,
            f"{_describe(lines, ctx)} should be billed within room, procedure or treatment cost",
        )
        return [
            Flag(
                flag_id=SUBSUMED_ITEM,
                rule_id=SUBSUMED_ITEM,
                kind=FlagKind.ADVISORY,
                severity=Severity.LOW,
                amount_at_risk=total(ctx.remaining[line.line_id] for line in lines),
                lines=line_ids(lines),
                citation_refs=CITATIONS,
                fix_code=FixCode.BILL_WITHIN_PACKAGE,
                trace_ref=step_id,
            )
        ]
    return _subsumed_dispute(facts, ctx, lines)


def _subsumed_dispute(facts: ClaimFacts, ctx: AuditContext, lines: list[BillLine]) -> list[Flag]:
    letter = facts.insurer_letter
    deductions = letter.deductions if letter else ()
    cut: list[tuple[BillLine, Paise]] = []
    for line in lines:
        amount = total(
            d.amount
            for d in deductions
            if d.line_id == line.line_id and d.reason is not DeductionReason.PROPORTIONATE
        )
        if amount:
            cut.append((line, Paise(min(amount, line.amount))))
    if not cut:
        return []
    gross = total(amount for _, amount in cut)
    recoverable = ctx.net_of_copay(gross)
    step_id = ctx.step(
        SUBSUMED_ITEM,
        f"Insurer deducted {format_inr(gross)} for items subsumed into other charges; "
        f"recoverable net of co-pay {format_inr(recoverable)}",
        result=recoverable,
        inputs={"gross": gross},
    )
    return [
        Flag(
            flag_id=SUBSUMED_ITEM,
            rule_id=SUBSUMED_ITEM,
            kind=FlagKind.DISPUTE,
            severity=Severity.MEDIUM,
            amount_at_risk=gross,
            recoverable=recoverable,
            lines=line_ids(line for line, _ in cut),
            citation_refs=CITATIONS,
            fix_code=FixCode.FILE_APPEAL,
            appealable=True,
            trace_ref=step_id,
        )
    ]
