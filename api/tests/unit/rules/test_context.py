from decimal import Decimal

import pytest

from arzi.domain.enums import CopayBase, LineCategory
from arzi.domain.models import Copay
from arzi.domain.money import Paise, rupees
from arzi.rules.context import AuditContext, fmt_qty, policy_refs
from tests.builders import facts, line, policy

C = LineCategory


def _ctx(copay: Copay | None = None) -> AuditContext:
    return AuditContext.start(facts(line(1, C.ROOM, 1_000), policy_=policy(copay=copay)))


def test_cut_cannot_exceed_remaining_or_go_negative() -> None:
    ctx = _ctx()
    bill_line = ctx.facts.bill_lines[0]
    with pytest.raises(ValueError, match="remaining"):
        ctx.cut(bill_line, "X", rupees(1_001))
    with pytest.raises(ValueError, match="remaining"):
        ctx.cut(bill_line, "X", Paise(-1))


def test_zero_cut_records_nothing() -> None:
    ctx = _ctx()
    ctx.cut(ctx.facts.bill_lines[0], "X", Paise(0))
    assert ctx.deductions[1] == []
    ctx.cut(ctx.facts.bill_lines[0], "X", rupees(400))
    assert ctx.remaining[1] == rupees(600)
    assert ctx.cut_by(1, "X") == rupees(400)
    assert ctx.cut_by(1, "Y") == 0


def test_claim_cut_cannot_exceed_payable() -> None:
    ctx = _ctx()
    with pytest.raises(ValueError, match="payable"):
        ctx.cut_claim("COPAY", rupees(1_001))
    with pytest.raises(ValueError, match="payable"):
        ctx.cut_claim("COPAY", Paise(-1))
    ctx.cut_claim("COPAY", rupees(100))
    assert ctx.payable == rupees(900)


@pytest.mark.parametrize(
    ("copay", "expected"),
    [
        (None, rupees(1_000)),
        (Copay(pct=Decimal(10)), rupees(900)),
        (Copay(pct=Decimal(10), base=CopayBase.CLAIMED), rupees(1_000)),
    ],
)
def test_net_of_copay(copay: Copay | None, expected: Paise) -> None:
    assert _ctx(copay).net_of_copay(rupees(1_000)) == expected


def test_step_ids_are_sequential() -> None:
    ctx = _ctx()
    assert ctx.step("X", "a") == "T01"
    assert ctx.step("X", "b", result=Paise(1), inputs={"k": 1}) == "T02"
    assert ctx.trace[1].inputs == {"k": 1}


def test_policy_refs_dedupe_and_skip_unknown() -> None:
    assert policy_refs(["4.2", None, "4.3", "4.2"]) == ("policy:4.2", "policy:4.3")
    assert policy_refs([None]) == ()


def test_fmt_qty() -> None:
    assert fmt_qty(Decimal("4.000")) == "4"
    assert fmt_qty(Decimal("2.50")) == "2.5"
    assert fmt_qty(Decimal("10")) == "10"
