"""Claim lifecycle as an explicit state machine.

Status changes go through ``transition`` so an illegal move (e.g. exporting an unsigned
appeal) fails loudly in the domain instead of relying on every caller to check. Signing is
the human-in-the-loop gate: nothing reaches ``exported`` without passing ``signed``, and a
revision after signing goes back to drafting and needs a fresh signature.
"""

from enum import StrEnum
from types import MappingProxyType

from arzi.domain.enums import ClaimStatus as S


class ClaimEvent(StrEnum):
    UPLOAD_DOCUMENTS = "upload_documents"
    START_PROCESSING = "start_processing"
    COMPLETE_AUDIT = "complete_audit"
    FAIL = "fail"
    RETRY = "retry"
    REAUDIT = "reaudit"
    DRAFT_APPEAL = "draft_appeal"
    SUBMIT_FOR_REVIEW = "submit_for_review"
    REQUEST_CHANGES = "request_changes"
    SIGN = "sign"
    REVISE = "revise"
    EXPORT = "export"


E = ClaimEvent

TRANSITIONS: MappingProxyType[tuple[S, ClaimEvent], S] = MappingProxyType(
    {
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
)


class IllegalTransitionError(ValueError):
    def __init__(self, current: S, event: ClaimEvent) -> None:
        super().__init__(f"cannot {event} a claim that is {current}")
        self.current = current
        self.event = event


def transition(current: S, event: ClaimEvent) -> S:
    """The status after ``event``, or ``IllegalTransitionError`` if the move is not allowed."""
    try:
        return TRANSITIONS[(current, event)]
    except KeyError:
        raise IllegalTransitionError(current, event) from None


def allowed_events(current: S) -> frozenset[ClaimEvent]:
    """Events the UI may offer from ``current`` (drives which buttons are enabled)."""
    return frozenset(event for (state, event) in TRANSITIONS if state is current)
