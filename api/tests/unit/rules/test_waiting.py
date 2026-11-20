from decimal import Decimal

import pytest

from arzi.domain.enums import ClaimMode, FlagKind, InsurerLetterType, LineCategory, RejectionGround
from arzi.domain.models import Admission, Copay, InsurerLetter, WaitingCondition
from arzi.domain.money import rupees
from arzi.rules.engine import audit
from tests.builders import facts, line, policy
from tests.unit.rules.helpers import only, rule_ids

C = LineCategory
KNEE = Admission(diagnosis="Primary osteoarthritis, right knee", procedure="Total knee replacement")
PED_KNEE = WaitingCondition(condition="Osteoarthritis of knee", waiting_months=36, clause_id="5.2")


def _pre(cover: int, *conditions: WaitingCondition, specific: bool = False) -> list[str]:
    field = "specific_waiting" if specific else "ped_declared"
    result = audit(
        facts(
            line(1, C.SURGEON, 100_000),
            admission=KNEE,
            policy_=policy(continuous_cover_months=cover, **{field: conditions}),
        )
    )
    return rule_ids(result)


def test_ped_inside_waiting_period_is_a_critical_pre_submission_risk() -> None:
    result = audit(
        facts(
            line(1, C.SURGEON, 100_000),
            admission=KNEE,
            policy_=policy(
                continuous_cover_months=20,
                ped_declared=(PED_KNEE,),
                copay=Copay(pct=Decimal(10)),
            ),
        )
    )
    flag = only(result, "WAITING_PERIOD")
    assert flag.flag_id == "WAITING_PERIOD-1"
    assert flag.kind is FlagKind.ADVISORY
    assert flag.amount_at_risk == rupees(90_000)  # the whole net payable is exposed
    assert flag.citation_refs == ("IRDAI_PED_36M", "policy:5.2")
    assert result.totals.at_risk == rupees(10_000)  # advisory exposure is not a deduction


@pytest.mark.parametrize(("cover", "flagged"), [(35, True), (36, False), (40, False)])
def test_waiting_boundary_at_36_months(cover: int, flagged: bool) -> None:
    assert ("WAITING_PERIOD" in _pre(cover, PED_KNEE)) is flagged


def test_policy_waiting_above_36_months_is_capped() -> None:
    long_wait = WaitingCondition(condition="knee replacement", waiting_months=48)
    assert _pre(40, long_wait, specific=True) == []
    assert _pre(30, long_wait, specific=True) == ["WAITING_PERIOD"]


def test_unrelated_condition_is_ignored() -> None:
    assert _pre(1, WaitingCondition(condition="Cataract", waiting_months=24)) == []


def _rejected(
    cover: int,
    ground: RejectionGround,
    *,
    ped: tuple[WaitingCondition, ...] = (PED_KNEE,),
    specific: tuple[WaitingCondition, ...] = (),
    fraud: bool = False,
) -> list[str]:
    letter = InsurerLetter(
        type=InsurerLetterType.REJECTION,
        amount_claimed=rupees(100_000),
        rejection_ground=ground,
        fraud_alleged=fraud,
    )
    result = audit(
        facts(
            line(1, C.SURGEON, 100_000),
            mode=ClaimMode.POST_REJECTION,
            letter=letter,
            admission=KNEE,
            policy_=policy(
                continuous_cover_months=cover, ped_declared=ped, specific_waiting=specific
            ),
        )
    )
    return rule_ids(result)


@pytest.mark.parametrize(("cover", "invalid"), [(35, False), (36, True), (40, True)])
def test_ped_rejection_is_invalid_once_the_wait_is_served(cover: int, invalid: bool) -> None:
    assert ("WAITING_REJECTION_INVALID" in _rejected(cover, RejectionGround.PED_WAITING)) is invalid


def test_ped_rejection_relief_is_the_engine_payable() -> None:
    letter = InsurerLetter(
        type=InsurerLetterType.REJECTION,
        amount_claimed=rupees(100_000),
        rejection_ground=RejectionGround.PED_WAITING,
    )
    result = audit(
        facts(
            line(1, C.SURGEON, 100_000),
            mode=ClaimMode.POST_REJECTION,
            letter=letter,
            admission=KNEE,
            policy_=policy(
                continuous_cover_months=40,
                ped_declared=(PED_KNEE,),
                copay=Copay(pct=Decimal(20)),
            ),
        )
    )
    flag = only(result, "WAITING_REJECTION_INVALID")
    assert flag.recoverable == rupees(80_000)
    assert result.totals.recoverable_on_appeal == rupees(80_000)
    assert flag.citation_refs == ("IRDAI_PED_36M", "policy:5.2")


def test_rejection_without_a_matching_condition_uses_the_statutory_maximum() -> None:
    assert _rejected(36, RejectionGround.PED_WAITING, ped=()) == ["WAITING_REJECTION_INVALID"]
    assert _rejected(35, RejectionGround.PED_WAITING, ped=()) == []


def test_specific_waiting_rejection_reads_the_specific_list() -> None:
    specific = (WaitingCondition(condition="knee replacement", waiting_months=24),)
    assert _rejected(24, RejectionGround.SPECIFIC_WAITING, ped=(), specific=specific) == [
        "WAITING_REJECTION_INVALID"
    ]
    assert _rejected(23, RejectionGround.SPECIFIC_WAITING, ped=(), specific=specific) == []


@pytest.mark.parametrize(
    ("cover", "fraud", "expected"),
    [(59, False, []), (60, False, ["MORATORIUM"]), (96, True, [])],
)
def test_moratorium_after_60_months_unless_fraud(
    cover: int, fraud: bool, expected: list[str]
) -> None:
    assert _rejected(cover, RejectionGround.NON_DISCLOSURE, fraud=fraud) == expected


def test_other_rejection_grounds_raise_nothing() -> None:
    assert _rejected(100, RejectionGround.OTHER) == []
