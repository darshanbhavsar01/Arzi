from decimal import Decimal

from arzi.domain.enums import CopayBase, LineCategory, RoomRentCapType
from arzi.domain.models import Admission, Copay, PerDayAmountCap, SubLimit
from arzi.domain.money import Paise, rupees
from arzi.rules.engine import audit
from tests.builders import facts, line, policy
from tests.unit.rules.helpers import line_cut, only, rule_ids

C = LineCategory
CATARACT = Admission(
    diagnosis="Senile cataract, left eye", procedure="Phacoemulsification with IOL"
)


def test_sub_limit_caps_the_whole_claim_and_splits_the_cut_pro_rata() -> None:
    limit = SubLimit(item="cataract", limit=rupees(40_000), clause_id="6.1")
    result = audit(
        facts(
            line(1, C.SURGEON, 30_000),
            line(2, C.IMPLANT, 20_000),
            admission=CATARACT,
            policy_=policy(sub_limits=(limit,)),
        )
    )
    flag = only(result, "SUB_LIMIT")
    assert flag.flag_id == "SUB_LIMIT-1"
    assert flag.amount_at_risk == rupees(10_000)
    assert flag.citation_refs == ("policy:6.1",)
    assert line_cut(result, 1, "SUB_LIMIT") == rupees(6_000)
    assert line_cut(result, 2, "SUB_LIMIT") == rupees(4_000)
    assert result.totals.predicted_payable == rupees(40_000)


def test_multiple_sub_limits_with_scopes() -> None:
    limits = (
        SubLimit(item="hernia", limit=rupees(1)),  # not this admission
        SubLimit(item="cataract", limit=rupees(15_000), categories=(C.IMPLANT,)),
        SubLimit(item="phacoemulsification", limit=rupees(60_000)),  # within limit
        SubLimit(item="cataract", limit=rupees(40_000)),
    )
    result = audit(
        facts(
            line(1, C.SURGEON, 30_000),
            line(2, C.IMPLANT, 20_000),
            admission=CATARACT,
            policy_=policy(sub_limits=limits),
        )
    )
    flags = [f for f in result.flags if f.rule_id == "SUB_LIMIT"]
    assert [(f.flag_id, f.amount_at_risk) for f in flags] == [
        ("SUB_LIMIT-2", rupees(5_000)),
        ("SUB_LIMIT-4", rupees(5_000)),
    ]
    assert flags[0].lines == (2,)
    assert result.totals.predicted_payable == rupees(40_000)


def test_sub_limit_applies_after_room_rent_cuts() -> None:
    cap = PerDayAmountCap(type=RoomRentCapType.PER_DAY_AMOUNT, amount=rupees(5_000))
    result = audit(
        facts(
            line(1, C.ROOM, 10_000),
            line(2, C.SURGEON, 40_000),
            admission=CATARACT,
            policy_=policy(
                room_rent_cap=cap, sub_limits=(SubLimit(item="cataract", limit=rupees(30_000)),)
            ),
        )
    )
    # room 5,000 + surgeon 20,000 = 25,000 admissible: under the 30,000 sub-limit
    assert rule_ids(result) == ["ROOM_RENT_EXCESS", "PROP_ROOM_RENT"]
    assert result.totals.predicted_payable == rupees(25_000)


def test_copay_on_admissible_and_on_claimed() -> None:
    bill = (line(1, C.SURGEON, 9_000), line(2, C.NON_PAYABLE, 1_000, description="Laundry"))
    on_admissible = audit(facts(*bill, policy_=policy(copay=Copay(pct=Decimal(10)))))
    on_claimed = audit(
        facts(*bill, policy_=policy(copay=Copay(pct=Decimal(10), base=CopayBase.CLAIMED)))
    )
    assert only(on_admissible, "COPAY").amount_at_risk == rupees(900)
    assert only(on_claimed, "COPAY").amount_at_risk == rupees(1_000)
    assert "claimed" in on_claimed.trace[-1].formula


def test_copay_never_exceeds_payable() -> None:
    result = audit(
        facts(
            line(1, C.SURGEON, 100),
            line(2, C.NON_PAYABLE, 900, description="Laundry"),
            policy_=policy(copay=Copay(pct=Decimal(50), base=CopayBase.CLAIMED)),
        )
    )
    assert only(result, "COPAY").amount_at_risk == rupees(100)
    assert result.totals.predicted_payable == 0


def test_copay_rounds_half_up_at_the_half_paisa() -> None:
    result = audit(
        facts(
            line(1, C.SURGEON, 0).model_copy(update={"amount": Paise(10_000_005)}),
            policy_=policy(copay=Copay(pct=Decimal(10))),
        )
    )
    assert only(result, "COPAY").amount_at_risk == Paise(1_000_001)


def test_zero_copay_raises_no_flag() -> None:
    assert (
        audit(facts(line(1, C.SURGEON, 1_000), policy_=policy(copay=Copay(pct=Decimal(0))))).flags
        == ()
    )
    assert (
        audit(facts(line(1, C.SURGEON, 0), policy_=policy(copay=Copay(pct=Decimal(10))))).flags
        == ()
    )
