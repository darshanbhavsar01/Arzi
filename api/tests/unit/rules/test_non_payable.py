from decimal import Decimal

from arzi.domain.enums import (
    ClaimMode,
    DeductionReason,
    FlagKind,
    InsurerLetterType,
    IrdaiList,
    LineCategory,
)
from arzi.domain.models import Copay, InsurerDeduction, InsurerLetter
from arzi.domain.money import rupees
from arzi.rules.engine import audit
from tests.builders import facts, line, policy
from tests.unit.rules.helpers import only, rule_ids

C = LineCategory


def _letter(*deductions: InsurerDeduction) -> InsurerLetter:
    return InsurerLetter(
        type=InsurerLetterType.DEDUCTION, amount_claimed=rupees(1), deductions=deductions
    )


def _cut(line_id: int, amount: int, reason: DeductionReason) -> InsurerDeduction:
    return InsurerDeduction(line_id=line_id, amount=rupees(amount), reason=reason)


def test_list_i_lines_are_cut_in_full() -> None:
    result = audit(
        facts(
            line(1, C.SURGEON, 10_000),
            line(2, C.NON_PAYABLE, 1_200, description="Laundry charges"),
            line(3, C.OTHER, 300, description="Baby food"),
        )
    )
    flag = only(result, "NON_PAYABLE")
    assert flag.amount_at_risk == rupees(1_500)
    assert flag.lines == (2, 3)
    assert flag.citation_refs == ("IRDAI_NON_PAYABLE_ANNEX_I",)
    assert result.totals.predicted_payable == rupees(10_000)


def test_non_payable_addon_covers_list_i() -> None:
    result = audit(
        facts(
            line(1, C.NON_PAYABLE, 1_200, description="Laundry"),
            policy_=policy(non_payable_addon=True),
        )
    )
    assert result.flags == ()
    assert "add-on" in result.trace[0].formula


def test_category_hint_alone_never_cuts() -> None:
    """The extractor called it non-payable, but nothing in the reference list matches."""
    result = audit(facts(line(1, C.NON_PAYABLE, 900, description="Attendant pass")))
    assert result.flags == ()


def test_human_confirmation_wins_over_the_matcher() -> None:
    confirmed_not_listed = line(
        1, C.OTHER, 1_200, description="Laundry", confirmed_by_human=True, irdai_list=None
    )
    confirmed_list_i = line(
        2, C.OTHER, 700, description="Toiletries", confirmed_by_human=True, irdai_list=IrdaiList.I
    )
    unconfirmed_hint = line(3, C.OTHER, 500, description="Gown", irdai_list=IrdaiList.I)
    result = audit(facts(confirmed_not_listed, confirmed_list_i, unconfirmed_hint))
    assert only(result, "NON_PAYABLE").lines == (2,)


def test_subsumed_items_are_a_warning_before_filing() -> None:
    result = audit(facts(line(1, C.OTHER, 1_000, description="Registration charges")))
    flag = only(result, "SUBSUMED_ITEM")
    assert flag.kind is FlagKind.ADVISORY
    assert flag.amount_at_risk == rupees(1_000)
    assert result.totals.at_risk == 0


def test_separately_deducted_subsumed_item_is_recoverable_net_of_copay() -> None:
    letter = _letter(
        _cut(1, 1_500, DeductionReason.NON_PAYABLE),  # more than billed: capped at the line
        _cut(2, 100, DeductionReason.PROPORTIONATE),  # handled by PROP_WRONGLY_APPLIED
    )
    result = audit(
        facts(
            line(1, C.OTHER, 1_000, description="Registration charges"),
            line(2, C.OTHER, 400, description="Admission charges"),
            mode=ClaimMode.POST_DEDUCTION,
            letter=letter,
            policy_=policy(copay=Copay(pct=Decimal(10))),
        )
    )
    flag = only(result, "SUBSUMED_ITEM")
    assert flag.kind is FlagKind.DISPUTE
    assert flag.lines == (1,)
    assert flag.amount_at_risk == rupees(1_000)
    assert flag.recoverable == rupees(900)
    assert flag.appealable


def test_subsumed_item_not_deducted_is_not_flagged_after_settlement() -> None:
    result = audit(
        facts(
            line(1, C.OTHER, 1_000, description="Registration charges"),
            mode=ClaimMode.POST_DEDUCTION,
            letter=_letter(),
        )
    )
    assert "SUBSUMED_ITEM" not in rule_ids(result)
