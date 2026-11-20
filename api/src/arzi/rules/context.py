"""Working state for one audit: a per-line ledger of admissible amounts and the trace.

Rules run in a fixed order and each sees the amounts left by the rules before it, which is
how a line already cut as non-payable is never also prorated. Every cut goes through ``cut``
so the ledger can never go negative or cut more than was billed.
"""

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction

from arzi.domain.enums import CopayBase, LineCategory
from arzi.domain.models import BillLine, ClaimFacts, LineDeduction, TraceStep
from arzi.domain.money import Paise, percent_of, total

POLICY_REF_PREFIX = "policy:"


@dataclass(frozen=True, slots=True)
class RoomBreach:
    """Room charges above the cap, as the exact cap/rate ratio for proportionate cuts."""

    ratio: Fraction
    ratio_text: str


@dataclass
class AuditContext:
    facts: ClaimFacts
    remaining: dict[int, Paise]
    deductions: dict[int, list[LineDeduction]]
    claim_cuts: list[LineDeduction] = field(default_factory=list)
    trace: list[TraceStep] = field(default_factory=list)
    room_breach: RoomBreach | None = None

    @classmethod
    def start(cls, facts: ClaimFacts) -> "AuditContext":
        return cls(
            facts=facts,
            remaining={line.line_id: line.amount for line in facts.bill_lines},
            deductions={line.line_id: [] for line in facts.bill_lines},
        )

    @property
    def billed(self) -> Paise:
        return total(line.amount for line in self.facts.bill_lines)

    @property
    def lines_admissible(self) -> Paise:
        """Admissible amount before claim-level cuts such as co-pay."""
        return total(self.remaining.values())

    @property
    def payable(self) -> Paise:
        return Paise(self.lines_admissible - total(cut.amount for cut in self.claim_cuts))

    def open_lines(self, categories: Collection[LineCategory] | None = None) -> list[BillLine]:
        """Lines with something left to cut, optionally limited to ``categories``."""
        return [
            line
            for line in self.facts.bill_lines
            if self.remaining[line.line_id] > 0
            and (categories is None or line.category in categories)
        ]

    def cut(self, line: BillLine, rule_id: str, amount: Paise) -> None:
        if amount < 0 or amount > self.remaining[line.line_id]:
            raise ValueError("a cut must be between zero and the line's remaining amount")
        if amount:
            self.remaining[line.line_id] = Paise(self.remaining[line.line_id] - amount)
            self.deductions[line.line_id].append(LineDeduction(rule_id=rule_id, amount=amount))

    def cut_claim(self, rule_id: str, amount: Paise) -> None:
        if amount < 0 or amount > self.payable:
            raise ValueError("a claim-level cut must be between zero and the payable amount")
        self.claim_cuts.append(LineDeduction(rule_id=rule_id, amount=amount))

    def cut_by(self, line_id: int, rule_id: str) -> Paise:
        return total(d.amount for d in self.deductions[line_id] if d.rule_id == rule_id)

    def step(
        self,
        rule_id: str,
        formula: str,
        *,
        result: Paise | None = None,
        inputs: Mapping[str, int | str] | None = None,
    ) -> str:
        """Record a computation and return its id for the flag's ``trace_ref``."""
        step_id = f"T{len(self.trace) + 1:02d}"
        self.trace.append(
            TraceStep(
                step_id=step_id,
                rule_id=rule_id,
                formula=formula,
                inputs=dict(inputs or {}),
                result=result,
            )
        )
        return step_id

    def net_of_copay(self, gross: Paise) -> Paise:
        """What an insured actually gets back from ``gross``: co-pay on admissible still applies."""
        copay = self.facts.policy.copay
        if copay is None or copay.base is not CopayBase.ADMISSIBLE:
            return gross
        return Paise(gross - percent_of(gross, copay.pct))


def policy_refs(clause_ids: Iterable[str | None]) -> tuple[str, ...]:
    """Citation refs for policy clauses, deduplicated, in order, skipping unknown clauses."""
    return tuple(dict.fromkeys(f"{POLICY_REF_PREFIX}{c}" for c in clause_ids if c))


def fmt_qty(qty: Decimal) -> str:
    return format(qty.normalize(), "f")


def line_ids(lines: Iterable[BillLine]) -> tuple[int, ...]:
    return tuple(line.line_id for line in lines)
