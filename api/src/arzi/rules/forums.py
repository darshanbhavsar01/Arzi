"""Which grievance forums an appeal can go to, and what each one needs.

The escalation ladder (domain rules §2) is insurer GRO → Bima Bharosa → Insurance Ombudsman.
The Ombudsman hears a complaint only after the insurer rejected a written complaint, replied
unsatisfactorily, or did not reply within one month; it must be filed within one year of that;
and the claim must be worth at most ₹50 lakh. Pure and dated by the caller's ``today``, so the
same inputs always give the same checklist.
"""

import calendar
import datetime as dt

from pydantic import BaseModel, ConfigDict

from arzi.domain.enums import AppealForum, GroOutcome
from arzi.domain.money import Paise, format_inr, rupees

OMBUDSMAN_MAX_CLAIM = rupees(50_00_000)
GRO_RESPONSE_WINDOW = "about 15 days (verify)"
_AWAITING = frozenset({GroOutcome.PENDING, GroOutcome.NO_REPLY})


class _Value(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GroComplaint(_Value):
    """The written complaint already sent to the insurer, if any."""

    filed_on: dt.date
    outcome: GroOutcome
    replied_on: dt.date | None = None


class ForumCheck(_Value):
    code: str
    label: str
    met: bool | None
    """None when it cannot be known yet (no complaint on record)."""


class ForumOption(_Value):
    forum: AppealForum
    eligible: bool
    reason: str | None = None
    checks: tuple[ForumCheck, ...] = ()
    response_window: str | None = None
    citations: tuple[str, ...] = ()


def add_months(day: dt.date, months: int) -> dt.date:
    """Calendar months later, clamped to the month's last day (31 Jan + 1 month = 28/29 Feb)."""
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return day.replace(
        year=year, month=month, day=min(day.day, calendar.monthrange(year, month)[1])
    )


def forum_options(
    *, relief: Paise, today: dt.date, complaint: GroComplaint | None
) -> tuple[ForumOption, ...]:
    return (
        ForumOption(
            forum=AppealForum.INSURER_GRO,
            eligible=True,
            response_window=GRO_RESPONSE_WINDOW,
            citations=("INSURER_GRIEVANCE_15D",),
        ),
        ForumOption(forum=AppealForum.BIMA_BHAROSA, eligible=True, citations=("BIMA_BHAROSA",)),
        _ombudsman(relief, today, complaint),
    )


def _ombudsman(relief: Paise, today: dt.date, complaint: GroComplaint | None) -> ForumOption:
    limit = format_inr(OMBUDSMAN_MAX_CLAIM)
    checks = [
        ForumCheck(
            code="gro_complaint",
            label="A written complaint was made to the insurer first",
            met=complaint is not None,
        ),
        _response_check(today, complaint),
        _deadline_check(today, complaint),
        ForumCheck(
            code="claim_value",
            label=f"The amount in dispute is at most {limit}",
            met=relief <= OMBUDSMAN_MAX_CLAIM,
        ),
    ]
    unmet = next((c for c in checks if c.met is not True), None)
    return ForumOption(
        forum=AppealForum.OMBUDSMAN,
        eligible=unmet is None,
        reason=None if unmet is None else f"Not yet: {unmet.label[0].lower()}{unmet.label[1:]}.",
        checks=tuple(checks),
        citations=("OMBUDSMAN_RULES_2017",),
    )


def _response_check(today: dt.date, complaint: GroComplaint | None) -> ForumCheck:
    label = "The insurer rejected it, replied unsatisfactorily, or did not reply within 1 month"
    if complaint is None:
        return ForumCheck(code="insurer_response", label=label, met=None)
    if complaint.outcome in _AWAITING:
        waited = add_months(complaint.filed_on, 1)
        return ForumCheck(code="insurer_response", label=label, met=today >= waited)
    return ForumCheck(code="insurer_response", label=label, met=True)


def _deadline_check(today: dt.date, complaint: GroComplaint | None) -> ForumCheck:
    label = "Filed within 1 year of the insurer's reply, or of the month without one"
    if complaint is None:
        return ForumCheck(code="within_one_year", label=label, met=None)
    if complaint.outcome in _AWAITING:
        start = add_months(complaint.filed_on, 1)
    else:
        start = complaint.replied_on or complaint.filed_on
    return ForumCheck(code="within_one_year", label=label, met=today <= add_months(start, 12))
