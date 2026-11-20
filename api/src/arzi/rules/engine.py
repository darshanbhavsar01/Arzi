"""``audit(facts)``: the single deterministic source of every rupee figure Arzi produces.

Pure: the same facts always give the same flags, totals and trace, with no I/O and no model
calls. The LLM layers explain and cite these numbers; they never compute them.
"""

from arzi.domain.enums import ClaimMode, FixCode, FlagKind, InsurerLetterType
from arzi.domain.models import AuditResult, ClaimFacts, Flag, LineOutcome, Totals
from arzi.domain.money import Paise, format_inr, total
from arzi.rules.context import AuditContext
from arzi.rules.registry import RULES

ENGINE_VERSION = "rules-2026.11.1"
INSURER_COMPARISON = "INSURER_COMPARISON"

# Fixes that remove the cause of their flags, so they avoid every cut those flags carry.
# Other fixes (e.g. collect a non-payable from the patient) move a cost; they save nothing.
# Savings are gross of co-pay and only offered before filing, while the fix is still possible.
SAVING_FIXES = frozenset({FixCode.ROOM_DOWNGRADE_OR_CONSENT})


def audit(facts: ClaimFacts) -> AuditResult:
    ctx = AuditContext.start(facts)
    flags = [
        flag for spec in RULES if facts.mode in spec.modes for flag in spec.evaluate(facts, ctx)
    ]
    fixable = SAVING_FIXES if facts.mode is ClaimMode.PRE_SUBMISSION else frozenset()
    savings = {
        code: total(f.amount_at_risk for f in flags if f.fix_code is code) for code in fixable
    }
    flags = [_with_savings(f, savings) for f in flags]
    _compare_with_insurer(facts, ctx)
    payable = ctx.payable
    totals = Totals(
        billed=ctx.billed,
        predicted_payable=payable,
        at_risk=Paise(ctx.billed - payable),
        recoverable_on_appeal=total(f.recoverable for f in flags if f.kind is FlagKind.DISPUTE),
    )
    return AuditResult(
        engine_version=ENGINE_VERSION,
        mode=facts.mode,
        flags=tuple(flags),
        totals=totals,
        trace=tuple(ctx.trace),
        lines=tuple(
            LineOutcome(
                line_id=line.line_id,
                billed=line.amount,
                admissible=ctx.remaining[line.line_id],
                deductions=tuple(ctx.deductions[line.line_id]),
            )
            for line in facts.bill_lines
        ),
        fix_savings=total(savings.values()),
    )


def _with_savings(flag: Flag, savings: dict[FixCode, Paise]) -> Flag:
    if flag.fix_code is None or flag.fix_code not in savings:
        return flag
    return flag.model_copy(update={"fix_savings": savings[flag.fix_code]})


def _compare_with_insurer(facts: ClaimFacts, ctx: AuditContext) -> None:
    letter = facts.insurer_letter
    if letter is None or letter.type is not InsurerLetterType.DEDUCTION:
        return
    gap = Paise(ctx.payable - letter.amount_approved)
    ctx.step(
        INSURER_COMPARISON,
        f"Engine payable {format_inr(ctx.payable)} - insurer approved "
        f"{format_inr(letter.amount_approved)} = {format_inr(gap)}",
        result=gap,
        inputs={"insurer_approved": letter.amount_approved},
    )
