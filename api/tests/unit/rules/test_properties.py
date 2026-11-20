"""Invariants that must hold for every claim, not just the demo cases (AGENTS.md §8)."""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from arzi.domain.enums import (
    ClaimMode,
    CopayBase,
    DeductionReason,
    FlagKind,
    InsurerLetterType,
    LineCategory,
    RoomRentCapType,
)
from arzi.domain.models import (
    Admission,
    BillLine,
    ClaimFacts,
    Copay,
    IcuCap,
    InsurerDeduction,
    InsurerLetter,
    PctOfSumInsuredCap,
    PerDayAmountCap,
    SubLimit,
)
from arzi.domain.money import Paise
from arzi.rules.engine import audit
from arzi.rules.room_rent import NEVER_PRORATED
from tests.builders import facts, policy

C = LineCategory
MAX_PAISE = 10**9  # ₹1 crore per line keeps examples realistic and fast

descriptions = st.sampled_from(
    ["Surgeon fees", "Laundry charges", "Registration charges", "Crepe bandage", "Item", "Gown"]
)
amounts = st.integers(min_value=0, max_value=MAX_PAISE).map(Paise)
percents = st.decimals(min_value=0, max_value=50, places=2)


@st.composite
def bill_lines(draw: st.DrawFn, first_is_room: bool = False) -> tuple[BillLine, ...]:
    count = draw(st.integers(min_value=1, max_value=10))
    lines = []
    for line_id in range(1, count + 1):
        category = C.ROOM if first_is_room and line_id == 1 else draw(st.sampled_from(C))
        lines.append(
            BillLine(
                line_id=line_id,
                description=draw(descriptions),
                category=category,
                amount=draw(amounts),
                qty=Decimal(draw(st.integers(min_value=1, max_value=10))),
            )
        )
    return tuple(lines)


@st.composite
def claims(draw: st.DrawFn, first_is_room: bool = False) -> ClaimFacts:
    lines = draw(bill_lines(first_is_room=first_is_room))
    room_cap = draw(
        st.none()
        | st.builds(
            PerDayAmountCap,
            type=st.just(RoomRentCapType.PER_DAY_AMOUNT),
            amount=st.integers(min_value=0, max_value=10**7).map(Paise),
        )
        | st.builds(PctOfSumInsuredCap, type=st.just(RoomRentCapType.PCT_OF_SI), pct=percents)
    )
    copay = draw(st.none() | st.builds(Copay, pct=percents, base=st.sampled_from(CopayBase)))
    sub_limits = draw(
        st.lists(st.builds(SubLimit, item=st.just("surgery"), limit=amounts), max_size=2)
    )
    mode = draw(st.sampled_from([ClaimMode.PRE_SUBMISSION, ClaimMode.POST_DEDUCTION]))
    letter = None
    if mode is ClaimMode.POST_DEDUCTION:
        deductions = draw(
            st.lists(
                st.builds(
                    InsurerDeduction,
                    line_id=st.sampled_from([line.line_id for line in lines]),
                    amount=amounts,
                    reason=st.sampled_from(DeductionReason),
                ),
                max_size=5,
            )
        )
        letter = InsurerLetter(
            type=InsurerLetterType.DEDUCTION,
            amount_claimed=Paise(sum(line.amount for line in lines)),
            amount_approved=draw(amounts),
            deductions=tuple(deductions),
        )
    return facts(
        *lines,
        mode=mode,
        letter=letter,
        admission=Admission(procedure=draw(st.sampled_from(["Knee surgery", "Observation"]))),
        policy_=policy(
            room_rent_cap=room_cap,
            icu_cap=draw(st.none() | st.builds(IcuCap, amount_per_day=amounts)),
            copay=copay,
            sub_limits=tuple(sub_limits),
            non_payable_addon=draw(st.booleans()),
            associated_expense_categories=tuple(draw(st.sets(st.sampled_from(C)))),
        ),
    )


@settings(max_examples=300)
@given(claims())
def test_money_is_conserved_and_never_negative(facts_: ClaimFacts) -> None:
    result = audit(facts_)
    t = result.totals

    assert t.predicted_payable + t.at_risk == t.billed
    assert 0 <= t.at_risk <= t.billed
    assert t.predicted_payable >= 0
    deduction_total = sum(f.amount_at_risk for f in result.flags if f.kind is FlagKind.DEDUCTION)
    assert deduction_total == t.at_risk
    for outcome in result.lines:
        assert 0 <= outcome.admissible <= outcome.billed
        assert outcome.billed - outcome.admissible == sum(d.amount for d in outcome.deductions)


@settings(max_examples=300)
@given(claims())
def test_icu_pharmacy_diagnostics_implants_are_never_prorated(facts_: ClaimFacts) -> None:
    result = audit(facts_)
    by_id = {line.line_id: line for line in facts_.bill_lines}
    for outcome in result.lines:
        if by_id[outcome.line_id].category in NEVER_PRORATED:
            assert all(d.rule_id != "PROP_ROOM_RENT" for d in outcome.deductions)


@given(claims())
def test_audit_is_deterministic(facts_: ClaimFacts) -> None:
    assert audit(facts_) == audit(facts_)


@settings(max_examples=300)
@given(claims(first_is_room=True), st.integers(min_value=0, max_value=MAX_PAISE))
def test_a_higher_room_rate_never_lowers_at_risk(facts_: ClaimFacts, increase: int) -> None:
    room = facts_.bill_lines[0]
    dearer = room.model_copy(update={"amount": Paise(room.amount + increase)})
    pricier = facts_.model_copy(update={"bill_lines": (dearer, *facts_.bill_lines[1:])})

    assert audit(pricier).totals.at_risk >= audit(facts_).totals.at_risk
