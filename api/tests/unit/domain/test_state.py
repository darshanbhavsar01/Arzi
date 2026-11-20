import itertools

import pytest

from arzi.domain.enums import ClaimStatus as S
from arzi.domain.state import (
    TRANSITIONS,
    ClaimEvent,
    IllegalTransitionError,
    allowed_events,
    transition,
)

E = ClaimEvent

EXPECTED = {
    (S.DRAFT, E.UPLOAD_DOCUMENTS): S.DOCUMENTS_UPLOADED,
    (S.DOCUMENTS_UPLOADED, E.UPLOAD_DOCUMENTS): S.DOCUMENTS_UPLOADED,
    (S.DOCUMENTS_UPLOADED, E.START_PROCESSING): S.PROCESSING,
    (S.PROCESSING, E.COMPLETE_AUDIT): S.AUDITED,
    (S.PROCESSING, E.FAIL): S.FAILED,
    (S.FAILED, E.RETRY): S.DOCUMENTS_UPLOADED,
    (S.AUDITED, E.REAUDIT): S.PROCESSING,
    (S.AUDITED, E.DRAFT_APPEAL): S.APPEAL_DRAFTED,
    (S.APPEAL_DRAFTED, E.SUBMIT_FOR_REVIEW): S.IN_REVIEW,
    (S.IN_REVIEW, E.REQUEST_CHANGES): S.APPEAL_DRAFTED,
    (S.IN_REVIEW, E.SIGN): S.SIGNED,
    (S.SIGNED, E.REVISE): S.APPEAL_DRAFTED,
    (S.SIGNED, E.EXPORT): S.EXPORTED,
}


@pytest.mark.parametrize(
    ("current", "event"),
    list(itertools.product(S, E)),
    ids=lambda v: str(v),
)
def test_every_state_event_pair(current: S, event: ClaimEvent) -> None:
    """Exhaustive: each of the |states| x |events| pairs is either the expected move or illegal."""
    if (current, event) in EXPECTED:
        assert transition(current, event) is EXPECTED[(current, event)]
    else:
        with pytest.raises(IllegalTransitionError) as info:
            transition(current, event)
        assert info.value.current is current
        assert info.value.event is event


def test_table_matches_specification() -> None:
    assert dict(TRANSITIONS) == EXPECTED


def test_export_requires_a_signature() -> None:
    """No path reaches ``exported`` except through ``signed``."""
    predecessors = {state for (state, _), target in TRANSITIONS.items() if target is S.EXPORTED}
    assert predecessors == {S.SIGNED}


def test_every_state_is_reachable_from_draft() -> None:
    seen, frontier = {S.DRAFT}, [S.DRAFT]
    while frontier:
        state = frontier.pop()
        for event in allowed_events(state):
            target = transition(state, event)
            if target not in seen:
                seen.add(target)
                frontier.append(target)
    assert seen == set(S)


def test_allowed_events() -> None:
    assert allowed_events(S.IN_REVIEW) == {E.SIGN, E.REQUEST_CHANGES}
    assert allowed_events(S.EXPORTED) == frozenset()


def test_error_message_names_the_move() -> None:
    with pytest.raises(IllegalTransitionError, match="cannot export a claim that is draft"):
        transition(S.DRAFT, E.EXPORT)
