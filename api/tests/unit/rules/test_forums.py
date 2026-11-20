import datetime as dt

import pytest

from arzi.domain.enums import AppealForum, GroOutcome
from arzi.domain.money import rupees
from arzi.rules.forums import (
    GRO_RESPONSE_WINDOW,
    OMBUDSMAN_MAX_CLAIM,
    ForumOption,
    GroComplaint,
    add_months,
    forum_options,
)

TODAY = dt.date(2026, 11, 20)


def _ombudsman(relief: int, complaint: GroComplaint | None, today: dt.date = TODAY) -> ForumOption:
    options = forum_options(relief=rupees(relief), today=today, complaint=complaint)
    return {o.forum: o for o in options}[AppealForum.OMBUDSMAN]


def test_gro_and_bima_bharosa_are_always_open() -> None:
    gro, bima, _ = forum_options(relief=rupees(20_137), today=TODAY, complaint=None)
    assert gro.forum is AppealForum.INSURER_GRO
    assert gro.eligible
    assert gro.response_window == GRO_RESPONSE_WINDOW == "about 15 days (verify)"
    assert gro.citations == ("INSURER_GRIEVANCE_15D",)
    assert bima.forum is AppealForum.BIMA_BHAROSA
    assert bima.eligible
    assert bima.citations == ("BIMA_BHAROSA",)


def test_ombudsman_needs_a_complaint_to_the_insurer_first() -> None:
    option = _ombudsman(20_137, None)
    assert not option.eligible
    assert option.reason == "Not yet: a written complaint was made to the insurer first."
    assert [c.met for c in option.checks] == [False, None, None, True]
    assert option.citations == ("OMBUDSMAN_RULES_2017",)


def test_ombudsman_opens_after_a_rejection_within_a_year() -> None:
    complaint = GroComplaint(
        filed_on=dt.date(2026, 9, 1), outcome=GroOutcome.REJECTED, replied_on=dt.date(2026, 9, 12)
    )
    option = _ombudsman(20_137, complaint)
    assert option.eligible
    assert option.reason is None
    assert all(c.met for c in option.checks)


def test_ombudsman_deadline_is_one_year_from_the_reply() -> None:
    complaint = GroComplaint(filed_on=dt.date(2025, 9, 1), outcome=GroOutcome.UNSATISFACTORY)
    assert _ombudsman(20_137, complaint, today=dt.date(2026, 9, 1)).eligible
    late = _ombudsman(20_137, complaint, today=dt.date(2026, 9, 2))
    assert not late.eligible
    assert late.reason is not None
    assert "within 1 year" in late.reason


@pytest.mark.parametrize("outcome", [GroOutcome.NO_REPLY, GroOutcome.PENDING])
def test_ombudsman_without_a_reply_waits_one_month(outcome: GroOutcome) -> None:
    complaint = GroComplaint(filed_on=dt.date(2026, 10, 25), outcome=outcome)
    waiting = _ombudsman(20_137, complaint)
    assert not waiting.eligible
    assert waiting.checks[1].met is False
    assert _ombudsman(20_137, complaint, today=dt.date(2026, 11, 25)).eligible
    # The year runs from the end of that month.
    assert _ombudsman(20_137, complaint, today=dt.date(2027, 11, 25)).eligible
    assert not _ombudsman(20_137, complaint, today=dt.date(2027, 11, 26)).eligible


def test_ombudsman_takes_claims_up_to_fifty_lakh() -> None:
    complaint = GroComplaint(filed_on=dt.date(2026, 9, 1), outcome=GroOutcome.REJECTED)
    assert rupees(50_00_000) == OMBUDSMAN_MAX_CLAIM
    assert _ombudsman(50_00_000, complaint).eligible
    over = _ombudsman(50_00_001, complaint)
    assert not over.eligible
    assert over.reason == "Not yet: the amount in dispute is at most ₹50,00,000."


@pytest.mark.parametrize(
    ("day", "months", "expected"),
    [
        (dt.date(2026, 1, 31), 1, dt.date(2026, 2, 28)),
        (dt.date(2028, 1, 31), 1, dt.date(2028, 2, 29)),
        (dt.date(2026, 11, 15), 2, dt.date(2027, 1, 15)),
        (dt.date(2026, 3, 10), 12, dt.date(2027, 3, 10)),
    ],
)
def test_add_months_clamps_to_the_month_end(day: dt.date, months: int, expected: dt.date) -> None:
    assert add_months(day, months) == expected
