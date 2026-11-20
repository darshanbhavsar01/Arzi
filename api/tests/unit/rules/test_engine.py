import pytest

from arzi.domain.enums import ClaimMode, InsurerLetterType, LineCategory
from arzi.domain.models import InsurerLetter
from arzi.domain.money import rupees
from arzi.rules import disputes, limits, non_payable, room_rent, waiting
from arzi.rules.engine import ENGINE_VERSION, audit
from arzi.rules.reference import citations
from arzi.rules.registry import RULES
from tests.builders import facts, line

C = LineCategory


def test_registry_order_is_the_documented_pipeline() -> None:
    assert [spec.rule_id for spec in RULES] == [
        non_payable.NON_PAYABLE,
        non_payable.SUBSUMED_ITEM,
        room_rent.ROOM_RENT_EXCESS,
        room_rent.PROP_ROOM_RENT,
        room_rent.ICU_CAP,
        limits.SUB_LIMIT,
        limits.COPAY,
        waiting.WAITING_PERIOD,
        waiting.WAITING_REJECTION_INVALID,
        waiting.MORATORIUM,
        disputes.PROP_WRONGLY_APPLIED,
        "DOC_MISSING",
    ]


@pytest.mark.parametrize("spec", RULES, ids=lambda s: s.rule_id)
def test_every_rule_has_a_citation_source(spec: object) -> None:
    rule_id = getattr(spec, "rule_id", "")
    citation_ids: tuple[str, ...] = getattr(spec, "citation_ids", ())
    assert citation_ids or getattr(spec, "cites_policy", False), rule_id
    assert set(citation_ids) <= citations().keys(), rule_id


def test_rule_ids_are_unique() -> None:
    ids = [spec.rule_id for spec in RULES]
    assert len(ids) == len(set(ids))


def test_result_carries_engine_version_and_line_outcomes() -> None:
    result = audit(facts(line(1, C.SURGEON, 100), line(2, C.PHARMACY, 50)))
    assert result.engine_version == ENGINE_VERSION
    assert [(o.line_id, o.billed, o.admissible, o.deductions) for o in result.lines] == [
        (1, rupees(100), rupees(100), ()),
        (2, rupees(50), rupees(50), ()),
    ]
    assert result.fix_savings == 0


def test_query_letters_are_not_compared() -> None:
    letter = InsurerLetter(type=InsurerLetterType.QUERY, amount_claimed=rupees(100))
    result = audit(facts(line(1, C.SURGEON, 100), mode=ClaimMode.PRE_SUBMISSION, letter=letter))
    assert result.trace == ()
