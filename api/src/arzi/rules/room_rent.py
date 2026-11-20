"""Room-rent cap, proportionate deduction and ICU cap.

IRDAI/HLT/REG/CIR/151/06/2020 lets an insurer scale down only the policy's "associated
medical expenses" when the room is above the cap; pharmacy and consumables, implants and
devices, diagnostics and ICU charges are never prorated, whatever the policy wording says.
"""

from fractions import Fraction

from arzi.domain.enums import FixCode, FlagKind, LineCategory, Severity
from arzi.domain.models import (
    BillLine,
    CategoryCap,
    ClaimFacts,
    Flag,
    PctOfSumInsuredCap,
    PerDayAmountCap,
)
from arzi.domain.money import Paise, allocate, format_inr, percent_of, ratio_apply, scale, total
from arzi.rules.context import AuditContext, RoomBreach, fmt_qty, line_ids, policy_refs
from arzi.rules.matching import normalise

ROOM_RENT_EXCESS = "ROOM_RENT_EXCESS"
PROP_ROOM_RENT = "PROP_ROOM_RENT"
ICU_CAP = "ICU_CAP"

PROP_CITATIONS = ("IRDAI_PROP_DED_2020",)

NEVER_PRORATED = frozenset(
    {
        LineCategory.PHARMACY,
        LineCategory.CONSUMABLE,
        LineCategory.IMPLANT,
        LineCategory.DIAGNOSTICS,
        LineCategory.ICU,
    }
)
_NOT_ASSOCIATED = NEVER_PRORATED | {LineCategory.ROOM, LineCategory.NON_PAYABLE}


def prorated_categories(facts: ClaimFacts) -> frozenset[LineCategory]:
    """The policy's associated expenses, minus everything the regulator excludes."""
    return frozenset(facts.policy.associated_expense_categories) - _NOT_ASSOCIATED


def _cap_per_day(facts: ClaimFacts, ctx: AuditContext) -> Paise | None:
    cap = facts.policy.room_rent_cap
    if cap is None:
        return None
    if isinstance(cap, PerDayAmountCap):
        ctx.step(ROOM_RENT_EXCESS, f"Room-rent cap {format_inr(cap.amount)}/day", result=cap.amount)
        return cap.amount
    if isinstance(cap, PctOfSumInsuredCap):
        amount = percent_of(facts.policy.sum_insured, cap.pct)
        ctx.step(
            ROOM_RENT_EXCESS,
            f"{fmt_qty(cap.pct)}% × {format_inr(facts.policy.sum_insured)} sum insured "
            f"= {format_inr(amount)}/day room-rent cap",
            result=amount,
            inputs={"pct": fmt_qty(cap.pct), "sum_insured": facts.policy.sum_insured},
        )
        return amount
    return _category_cap(cap, facts, ctx)


def _category_cap(cap: CategoryCap, facts: ClaimFacts, ctx: AuditContext) -> Paise | None:
    wanted = normalise(cap.category)
    for category in facts.hospital.room_categories:
        if normalise(category.name) == wanted:
            ctx.step(
                ROOM_RENT_EXCESS,
                f"Eligible category '{cap.category}' is priced {format_inr(category.rate_per_day)}"
                "/day in the hospital tariff",
                result=category.rate_per_day,
            )
            return category.rate_per_day
    ctx.step(
        ROOM_RENT_EXCESS,
        f"Eligible category '{cap.category}' is not in the hospital tariff; "
        "room-rent checks need the tariff rate",
    )
    return None


def room_rent_excess(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """Room charges above the per-day cap are not payable: (billed - cap × days).

    The proportionate ratio is cap / per-day rate of the dearest room above the cap, i.e. the
    category actually occupied. Blending in cheaper, compliant days would let a higher rate
    on one line *improve* the ratio, which no insurer does.
    """
    rooms = ctx.open_lines({LineCategory.ROOM})
    cap = _cap_per_day(facts, ctx) if rooms else None
    if cap is None:
        return []
    excess_lines: list[tuple[BillLine, Paise, Paise]] = []
    step_id = ""
    for line in rooms:
        amount = ctx.remaining[line.line_id]
        allowance = scale(cap, line.qty)
        if amount > allowance:
            excess = Paise(amount - allowance)
            ctx.cut(line, ROOM_RENT_EXCESS, excess)
            excess_lines.append((line, amount, excess))
            step_id = ctx.step(
                ROOM_RENT_EXCESS,
                f"{format_inr(amount)} billed - {format_inr(cap)} × {fmt_qty(line.qty)} days "
                f"= {format_inr(excess)} above the cap",
                result=excess,
                inputs={"line_id": line.line_id, "cap_per_day": cap},
            )
    if not excess_lines:
        return []
    dearest, dearest_amount, _ = max(
        excess_lines, key=lambda e: Fraction(e[1]) / Fraction(e[0].qty)
    )
    ctx.room_breach = RoomBreach(
        ratio=Fraction(cap) * Fraction(dearest.qty) / dearest_amount,
        ratio_text=_ratio_text(cap, dearest, dearest_amount),
    )
    return [
        Flag(
            flag_id=ROOM_RENT_EXCESS,
            rule_id=ROOM_RENT_EXCESS,
            kind=FlagKind.DEDUCTION,
            severity=Severity.HIGH,
            amount_at_risk=total(excess for _, _, excess in excess_lines),
            lines=line_ids(line for line, _, _ in excess_lines),
            citation_refs=policy_refs([_room_clause(facts)]),
            fix_code=FixCode.ROOM_DOWNGRADE_OR_CONSENT,
            trace_ref=step_id,
        )
    ]


def _ratio_text(cap: Paise, room: BillLine, amount: Paise) -> str:
    """``cap / rate`` with the rate per day shown exactly, never rounded."""
    numerator, denominator = room.qty.as_integer_ratio()
    rate, remainder = divmod(amount * denominator, numerator)
    if remainder == 0:
        return f"{format_inr(cap)} / {format_inr(Paise(rate))}"
    return f"{format_inr(cap)} / ({format_inr(amount)} ÷ {fmt_qty(room.qty)} days)"


def _room_clause(facts: ClaimFacts) -> str | None:
    cap = facts.policy.room_rent_cap
    return cap.clause_id if cap else None


def proportionate_room_rent(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """Associated expenses × (cap / room rate); the rest is the proportionate cut."""
    breach = ctx.room_breach
    lines = ctx.open_lines(prorated_categories(facts)) if breach else []
    if breach is None or not lines:
        return []
    weights = [ctx.remaining[line.line_id] for line in lines]
    base = total(weights)
    payable = ratio_apply(base, breach.ratio.numerator, breach.ratio.denominator)
    ctx.step(
        PROP_ROOM_RENT,
        f"{format_inr(base)} associated expenses × {breach.ratio_text} = {format_inr(payable)}",
        result=payable,
        inputs={"ratio": str(breach.ratio)},
    )
    for line, weight, part in zip(lines, weights, allocate(payable, weights), strict=True):
        ctx.cut(line, PROP_ROOM_RENT, Paise(weight - part))
    amount_cut = Paise(base - payable)
    step_id = ctx.step(
        PROP_ROOM_RENT,
        f"{format_inr(base)} - {format_inr(payable)} = {format_inr(amount_cut)} "
        "proportionate deduction",
        result=amount_cut,
    )
    return [
        Flag(
            flag_id=PROP_ROOM_RENT,
            rule_id=PROP_ROOM_RENT,
            kind=FlagKind.DEDUCTION,
            severity=Severity.HIGH,
            amount_at_risk=amount_cut,
            lines=line_ids(lines),
            citation_refs=(
                *PROP_CITATIONS,
                *policy_refs([facts.policy.proportionate_clause_id, _room_clause(facts)]),
            ),
            fix_code=FixCode.ROOM_DOWNGRADE_OR_CONSENT,
            trace_ref=step_id,
        )
    ]


def icu_cap(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """ICU above its per-day cap loses only the excess; ICU is never prorated."""
    cap = facts.policy.icu_cap
    lines = ctx.open_lines({LineCategory.ICU}) if cap else []
    if cap is None or not lines:
        return []
    flagged = []
    step_id = ""
    for line in lines:
        amount = ctx.remaining[line.line_id]
        allowance = scale(cap.amount_per_day, line.qty)
        if amount > allowance:
            excess = Paise(amount - allowance)
            ctx.cut(line, ICU_CAP, excess)
            flagged.append((line, excess))
            step_id = ctx.step(
                ICU_CAP,
                f"{format_inr(amount)} billed - {format_inr(cap.amount_per_day)} × "
                f"{fmt_qty(line.qty)} days = {format_inr(excess)} above the ICU cap",
                result=excess,
                inputs={"line_id": line.line_id},
            )
    if not flagged:
        return []
    return [
        Flag(
            flag_id=ICU_CAP,
            rule_id=ICU_CAP,
            kind=FlagKind.DEDUCTION,
            severity=Severity.MEDIUM,
            amount_at_risk=total(excess for _, excess in flagged),
            lines=line_ids(line for line, _ in flagged),
            citation_refs=policy_refs([cap.clause_id]),
            fix_code=FixCode.ICU_TARIFF_REVIEW,
            trace_ref=step_id,
        )
    ]
