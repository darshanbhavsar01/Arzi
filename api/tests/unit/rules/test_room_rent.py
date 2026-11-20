from decimal import Decimal

from arzi.domain.enums import LineCategory, RoomRentCapType
from arzi.domain.models import (
    CategoryCap,
    Hospital,
    IcuCap,
    PctOfSumInsuredCap,
    PerDayAmountCap,
    RoomCategory,
)
from arzi.domain.money import rupees
from arzi.rules.engine import audit
from tests.builders import facts, line, policy
from tests.unit.rules.helpers import line_cut, only, rule_ids

C = LineCategory


def _cap(amount: int, clause: str | None = "4.2") -> PerDayAmountCap:
    return PerDayAmountCap(
        type=RoomRentCapType.PER_DAY_AMOUNT, amount=rupees(amount), clause_id=clause
    )


def test_no_cap_means_no_room_flags() -> None:
    result = audit(facts(line(1, C.ROOM, 80_000, qty=4), line(2, C.SURGEON, 60_000)))
    assert rule_ids(result) == []
    assert result.totals.at_risk == 0


def test_cap_equal_to_rate_raises_nothing() -> None:
    result = audit(
        facts(
            line(1, C.ROOM, 20_000, qty=4),
            line(2, C.SURGEON, 60_000),
            policy_=policy(room_rent_cap=_cap(5_000)),
        )
    )
    assert rule_ids(result) == []
    assert result.trace[0].formula == "Room-rent cap ₹5,000/day"


def test_no_room_line_skips_cap_resolution() -> None:
    result = audit(facts(line(1, C.SURGEON, 60_000), policy_=policy(room_rent_cap=_cap(5_000))))
    assert result.flags == ()
    assert result.trace == ()


def test_pct_of_sum_insured_cap() -> None:
    cap = PctOfSumInsuredCap(type=RoomRentCapType.PCT_OF_SI, pct=Decimal(1), clause_id="4.2")
    result = audit(
        facts(
            line(1, C.ROOM, 32_000, qty=4),
            line(2, C.SURGEON, 60_000),
            policy_=policy(room_rent_cap=cap, sum_insured=rupees(500_000)),
        )
    )
    assert only(result, "ROOM_RENT_EXCESS").amount_at_risk == rupees(12_000)
    assert only(result, "PROP_ROOM_RENT").amount_at_risk == rupees(22_500)
    assert result.trace[0].formula == "1% × ₹5,00,000 sum insured = ₹5,000/day room-rent cap"


def test_category_cap_uses_the_hospital_tariff() -> None:
    hospital = Hospital(
        name="Sanjeevani Multispeciality Hospital",
        room_categories=(
            RoomCategory(name="General ward", rate_per_day=rupees(2_000)),
            RoomCategory(name="Twin Sharing", rate_per_day=rupees(4_000)),
        ),
    )
    cap = CategoryCap(type=RoomRentCapType.CATEGORY, category="twin-sharing", clause_id="4.2")
    result = audit(
        facts(
            line(1, C.ROOM, 24_000, qty=3),
            line(2, C.NURSING, 6_000),
            policy_=policy(room_rent_cap=cap),
            hospital=hospital,
        )
    )
    assert only(result, "ROOM_RENT_EXCESS").amount_at_risk == rupees(12_000)
    assert only(result, "PROP_ROOM_RENT").amount_at_risk == rupees(3_000)


def test_category_cap_missing_from_tariff_is_traced_not_guessed() -> None:
    cap = CategoryCap(type=RoomRentCapType.CATEGORY, category="Deluxe")
    result = audit(facts(line(1, C.ROOM, 24_000, qty=3), policy_=policy(room_rent_cap=cap)))
    assert result.flags == ()
    assert "not in the hospital tariff" in result.trace[0].formula


def test_multiple_room_lines_use_the_dearest_room_for_the_ratio() -> None:
    result = audit(
        facts(
            line(1, C.ROOM, 12_000, qty=2),  # ₹6,000/day, above cap
            line(2, C.ROOM, 8_000, qty=1),  # ₹8,000/day, above cap: the ratio comes from here
            line(3, C.ROOM, 8_000, qty=2),  # ₹4,000/day, within cap
            line(4, C.SURGEON, 48_000),
            policy_=policy(room_rent_cap=_cap(5_000)),
        )
    )
    excess = only(result, "ROOM_RENT_EXCESS")
    assert excess.amount_at_risk == rupees(5_000)
    assert excess.lines == (1, 2)
    assert only(result, "PROP_ROOM_RENT").amount_at_risk == rupees(18_000)  # 48,000 × 3/8
    assert "× ₹5,000 / ₹8,000 =" in result.trace[3].formula


def test_inexact_per_day_rate_is_shown_as_a_division() -> None:
    result = audit(
        facts(
            line(1, C.ROOM, 20_000, qty=3),
            line(2, C.SURGEON, 30_000),
            policy_=policy(room_rent_cap=_cap(5_000)),
        )
    )
    assert only(result, "ROOM_RENT_EXCESS").amount_at_risk == rupees(5_000)
    assert only(result, "PROP_ROOM_RENT").amount_at_risk == rupees(7_500)
    assert "× ₹5,000 / (₹20,000 ÷ 3 days) = ₹22,500" in result.trace[2].formula


def test_fractional_days() -> None:
    result = audit(
        facts(line(1, C.ROOM, 20_000, qty="2.5"), policy_=policy(room_rent_cap=_cap(5_000)))
    )
    assert only(result, "ROOM_RENT_EXCESS").amount_at_risk == rupees(7_500)
    assert "× 2.5 days" in result.trace[1].formula


def test_never_prorated_even_if_the_policy_lists_them_as_associated() -> None:
    associated = (C.SURGEON, C.PHARMACY, C.ICU, C.DIAGNOSTICS, C.IMPLANT, C.CONSUMABLE)
    result = audit(
        facts(
            line(1, C.ROOM, 8_000),
            line(2, C.SURGEON, 10_000),
            line(3, C.PHARMACY, 10_000),
            line(4, C.ICU, 10_000),
            line(5, C.DIAGNOSTICS, 10_000),
            line(6, C.IMPLANT, 10_000),
            line(7, C.CONSUMABLE, 10_000),
            policy_=policy(room_rent_cap=_cap(4_000), associated_expense_categories=associated),
        )
    )
    assert only(result, "PROP_ROOM_RENT").lines == (2,)
    assert all(line_cut(result, i, "PROP_ROOM_RENT") == 0 for i in range(3, 8))


def test_breach_without_associated_lines_has_no_proportionate_flag() -> None:
    result = audit(
        facts(
            line(1, C.ROOM, 8_000),
            line(2, C.PHARMACY, 10_000),
            policy_=policy(room_rent_cap=_cap(4_000)),
        )
    )
    assert rule_ids(result) == ["ROOM_RENT_EXCESS"]


def test_proportionate_cites_circular_and_policy_clauses() -> None:
    result = audit(
        facts(
            line(1, C.ROOM, 8_000),
            line(2, C.SURGEON, 10_000),
            policy_=policy(room_rent_cap=_cap(4_000, clause=None), proportionate_clause_id="4.3"),
        )
    )
    assert only(result, "PROP_ROOM_RENT").citation_refs == ("IRDAI_PROP_DED_2020", "policy:4.3")
    assert only(result, "ROOM_RENT_EXCESS").citation_refs == ()


def test_icu_cap_cuts_only_the_excess() -> None:
    result = audit(
        facts(
            line(1, C.ICU, 30_000, qty=2),
            line(2, C.ICU, 9_000, qty=1),
            line(3, C.SURGEON, 50_000),
            policy_=policy(icu_cap=IcuCap(amount_per_day=rupees(10_000), clause_id="4.4")),
        )
    )
    flag = only(result, "ICU_CAP")
    assert flag.amount_at_risk == rupees(10_000)
    assert flag.lines == (1,)
    assert flag.citation_refs == ("policy:4.4",)
    assert result.totals.at_risk == rupees(10_000)


def test_icu_within_cap_or_without_cap() -> None:
    within = policy(icu_cap=IcuCap(amount_per_day=rupees(20_000)))
    assert audit(facts(line(1, C.ICU, 15_000), policy_=within)).flags == ()
    assert audit(facts(line(1, C.ICU, 15_000))).flags == ()
    assert audit(facts(line(1, C.SURGEON, 15_000), policy_=within)).flags == ()
