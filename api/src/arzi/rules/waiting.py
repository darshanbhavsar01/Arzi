"""Waiting periods and the moratorium (IRDAI norms effective 1 April 2024).

PED and specific-disease waiting periods are capped at 36 months whatever the policy says,
and after 60 months of continuous cover a claim cannot be contested for non-disclosure
unless fraud is proven. A cover equal to the waiting period means the wait is complete.
"""

from collections.abc import Iterable

from arzi.domain.enums import FixCode, FlagKind, RejectionGround, Severity
from arzi.domain.models import ClaimFacts, Flag, WaitingCondition
from arzi.rules.context import AuditContext, policy_refs
from arzi.rules.matching import mentions

WAITING_PERIOD = "WAITING_PERIOD"
WAITING_REJECTION_INVALID = "WAITING_REJECTION_INVALID"
MORATORIUM = "MORATORIUM"

PED_CITATIONS = ("IRDAI_PED_36M",)
MORATORIUM_CITATIONS = ("IRDAI_MORATORIUM_60M",)

MAX_WAITING_MONTHS = 36
MORATORIUM_MONTHS = 60


def _matching(conditions: Iterable[WaitingCondition], facts: ClaimFacts) -> list[WaitingCondition]:
    texts = (facts.admission.diagnosis, facts.admission.procedure)
    return [condition for condition in conditions if mentions(condition.condition, texts)]


def waiting_period(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """Before filing: a matching condition still inside its waiting period risks the claim."""
    cover = facts.policy.continuous_cover_months
    conditions = (*facts.policy.ped_declared, *facts.policy.specific_waiting)
    flags = []
    for number, condition in enumerate(_matching(conditions, facts), start=1):
        effective = min(condition.waiting_months, MAX_WAITING_MONTHS)
        if cover >= effective:
            continue
        step_id = ctx.step(
            WAITING_PERIOD,
            f"'{condition.condition}': cover {cover} months < waiting "
            f"min({condition.waiting_months}, {MAX_WAITING_MONTHS}) = {effective} months",
            inputs={"cover_months": cover, "waiting_months": effective},
        )
        flags.append(
            Flag(
                flag_id=f"{WAITING_PERIOD}-{number}",
                rule_id=WAITING_PERIOD,
                kind=FlagKind.ADVISORY,
                severity=Severity.CRITICAL,
                amount_at_risk=ctx.payable,
                citation_refs=(*PED_CITATIONS, *policy_refs([condition.clause_id])),
                fix_code=FixCode.CHECK_WAITING_PERIOD,
                trace_ref=step_id,
            )
        )
    return flags


def waiting_rejection_invalid(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """After a PED or specific-waiting rejection: invalid once cover reaches the capped wait."""
    letter = facts.insurer_letter
    ground = letter.rejection_ground if letter else None
    if ground not in (RejectionGround.PED_WAITING, RejectionGround.SPECIFIC_WAITING):
        return []
    pool = (
        facts.policy.ped_declared
        if ground is RejectionGround.PED_WAITING
        else facts.policy.specific_waiting
    )
    matched = _matching(pool, facts)
    policy_waiting = max((c.waiting_months for c in matched), default=MAX_WAITING_MONTHS)
    effective = min(policy_waiting, MAX_WAITING_MONTHS)
    cover = facts.policy.continuous_cover_months
    formula = (
        f"Continuous cover {cover} months vs waiting min({policy_waiting}, {MAX_WAITING_MONTHS})"
        f" = {effective} months"
    )
    inputs: dict[str, int | str] = {"cover_months": cover, "waiting_months": effective}
    if cover < effective:
        ctx.step(
            WAITING_REJECTION_INVALID, f"{formula}: waiting period not yet served", inputs=inputs
        )
        return []
    payable = ctx.payable
    step_id = ctx.step(
        WAITING_REJECTION_INVALID,
        f"{formula}: waiting period served, rejection is not supported",
        result=payable,
        inputs=inputs,
    )
    return [
        Flag(
            flag_id=WAITING_REJECTION_INVALID,
            rule_id=WAITING_REJECTION_INVALID,
            kind=FlagKind.DISPUTE,
            severity=Severity.HIGH,
            amount_at_risk=payable,
            recoverable=payable,
            citation_refs=(*PED_CITATIONS, *policy_refs(c.clause_id for c in matched)),
            fix_code=FixCode.FILE_APPEAL,
            appealable=True,
            trace_ref=step_id,
        )
    ]


def moratorium(facts: ClaimFacts, ctx: AuditContext) -> list[Flag]:
    """No non-disclosure rejection after 60 months of cover unless fraud is alleged."""
    letter = facts.insurer_letter
    cover = facts.policy.continuous_cover_months
    if letter is None or letter.rejection_ground is not RejectionGround.NON_DISCLOSURE:
        return []
    if cover < MORATORIUM_MONTHS:
        return []
    if letter.fraud_alleged:
        ctx.step(
            MORATORIUM,
            f"Cover {cover} months ≥ {MORATORIUM_MONTHS}, but the insurer alleges fraud: "
            "the moratorium does not protect proven fraud",
        )
        return []
    payable = ctx.payable
    step_id = ctx.step(
        MORATORIUM,
        f"Cover {cover} months ≥ {MORATORIUM_MONTHS}-month moratorium and no fraud alleged: "
        "non-disclosure cannot be contested",
        result=payable,
        inputs={"cover_months": cover},
    )
    return [
        Flag(
            flag_id=MORATORIUM,
            rule_id=MORATORIUM,
            kind=FlagKind.DISPUTE,
            severity=Severity.HIGH,
            amount_at_risk=payable,
            recoverable=payable,
            citation_refs=MORATORIUM_CITATIONS,
            fix_code=FixCode.FILE_APPEAL,
            appealable=True,
            trace_ref=step_id,
        )
    ]
