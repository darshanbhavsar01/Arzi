"""The ordered rule registry.

Order is part of the semantics, because each rule sees what earlier rules left payable:
non-payables → room/ICU caps + proportionate → sub-limits → co-pay → waiting periods →
insurer comparisons → documents. Waiting-period and dispute rules come after co-pay because
their exposure and relief are the net payable amount.
"""

from collections.abc import Callable
from dataclasses import dataclass

from arzi.domain.enums import ClaimMode
from arzi.domain.models import ClaimFacts, Flag
from arzi.rules import disputes, documents, limits, non_payable, room_rent, waiting
from arzi.rules.context import AuditContext

Rule = Callable[[ClaimFacts, AuditContext], list[Flag]]

ALL_MODES = frozenset(ClaimMode)
PRE = frozenset({ClaimMode.PRE_SUBMISSION})
DEDUCTION = frozenset({ClaimMode.POST_DEDUCTION})
REJECTION = frozenset({ClaimMode.POST_REJECTION})


@dataclass(frozen=True, slots=True)
class RuleSpec:
    """A rule plus what it may cite: regulator refs and/or the policy clause it reads."""

    rule_id: str
    evaluate: Rule
    citation_ids: tuple[str, ...] = ()
    cites_policy: bool = False
    modes: frozenset[ClaimMode] = ALL_MODES


RULES: tuple[RuleSpec, ...] = (
    RuleSpec(non_payable.NON_PAYABLE, non_payable.non_payable, non_payable.CITATIONS),
    RuleSpec(
        non_payable.SUBSUMED_ITEM,
        non_payable.subsumed_item,
        non_payable.CITATIONS,
        modes=PRE | DEDUCTION,
    ),
    RuleSpec(room_rent.ROOM_RENT_EXCESS, room_rent.room_rent_excess, cites_policy=True),
    RuleSpec(
        room_rent.PROP_ROOM_RENT,
        room_rent.proportionate_room_rent,
        room_rent.PROP_CITATIONS,
        cites_policy=True,
    ),
    RuleSpec(room_rent.ICU_CAP, room_rent.icu_cap, cites_policy=True),
    RuleSpec(limits.SUB_LIMIT, limits.sub_limit, cites_policy=True),
    RuleSpec(limits.COPAY, limits.copay, cites_policy=True),
    RuleSpec(
        waiting.WAITING_PERIOD,
        waiting.waiting_period,
        waiting.PED_CITATIONS,
        cites_policy=True,
        modes=PRE,
    ),
    RuleSpec(
        waiting.WAITING_REJECTION_INVALID,
        waiting.waiting_rejection_invalid,
        waiting.PED_CITATIONS,
        cites_policy=True,
        modes=REJECTION,
    ),
    RuleSpec(
        waiting.MORATORIUM,
        waiting.moratorium,
        waiting.MORATORIUM_CITATIONS,
        modes=REJECTION,
    ),
    RuleSpec(
        disputes.PROP_WRONGLY_APPLIED,
        disputes.prop_wrongly_applied,
        room_rent.PROP_CITATIONS,
        modes=DEDUCTION,
    ),
    RuleSpec(documents.DOC_MISSING, documents.doc_missing, cites_policy=True),
)
