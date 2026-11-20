"""Post-deduction checks that compare the insurer's letter with the engine, line by line."""

from arzi.domain.enums import DeductionReason, FixCode, FlagKind, Severity
from arzi.domain.models import BillLine, ClaimFacts, Flag
from arzi.domain.money import Paise, format_inr, total
from arzi.rules.context import AuditContext, line_ids
from arzi.rules.room_rent import PROP_CITATIONS, PROP_ROOM_RENT

PROP_WRONGLY_APPLIED = "PROP_WRONGLY_APPLIED"


def prop_wrongly_applied(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """A proportionate cut on any line the engine does not prorate is recoverable in full.

    That covers the common error (ratio applied to pharmacy, diagnostics, implants or ICU) and
    prorating when the room was within the cap. Over-cuts on correctly prorated lines are not
    claimed here.
    """
    letter = facts.insurer_letter
    deductions = letter.deductions if letter else ()
    wrong: list[tuple[BillLine, Paise]] = []
    for line in facts.bill_lines:
        if ctx.cut_by(line.line_id, PROP_ROOM_RENT):
            continue
        amount = total(
            d.amount
            for d in deductions
            if d.line_id == line.line_id and d.reason is DeductionReason.PROPORTIONATE
        )
        if amount:
            wrong.append((line, Paise(min(amount, line.amount))))
    if not wrong:
        return []
    gross = total(amount for _, amount in wrong)
    recoverable = ctx.net_of_copay(gross)
    detail = " + ".join(f"{line.description} {format_inr(amount)}" for line, amount in wrong)
    step_id = ctx.step(
        PROP_WRONGLY_APPLIED,
        f"Proportionate deduction on lines that may not be prorated: {detail} = "
        f"{format_inr(gross)}; recoverable net of co-pay {format_inr(recoverable)}",
        result=recoverable,
        inputs={"gross": gross},
    )
    return [
        Flag(
            flag_id=PROP_WRONGLY_APPLIED,
            rule_id=PROP_WRONGLY_APPLIED,
            kind=FlagKind.DISPUTE,
            severity=Severity.HIGH,
            amount_at_risk=gross,
            recoverable=recoverable,
            lines=line_ids(line for line, _ in wrong),
            citation_refs=PROP_CITATIONS,
            fix_code=FixCode.FILE_APPEAL,
            appealable=True,
            trace_ref=step_id,
        )
    ]
