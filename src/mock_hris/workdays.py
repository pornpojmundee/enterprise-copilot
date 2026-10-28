"""Working-day arithmetic shared by the seed generator and the mock HRIS API.

Nawa Tech leave rule (docs: HR-001 §4): leave is counted in working days only —
Saturdays, Sundays and company holidays (including substitution days) are not deducted.
Pure functions, no I/O, so they are easy to unit-test.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

HALF_DAY_VALUES = {"am", "pm"}


def is_working_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def iter_days(start: date, end: date) -> Iterable[date]:
    if end < start:
        raise ValueError("end date is before start date")
    for i in range((end - start).days + 1):
        yield start + timedelta(days=i)


def count_working_days(
    start: date, end: date, holidays: set[date], half_day: str | None = None
) -> float:
    """Number of leave days deducted for the range [start, end] (inclusive).

    half_day ('am' / 'pm') is only valid for a single-day request and counts as 0.5.
    """
    if half_day is not None:
        if half_day not in HALF_DAY_VALUES:
            raise ValueError("half_day must be 'am' or 'pm'")
        if start != end:
            raise ValueError("half-day leave must start and end on the same date")
        return 0.5 if is_working_day(start, holidays) else 0.0
    return float(sum(1 for d in iter_days(start, end) if is_working_day(d, holidays)))


def breakdown(start: date, end: date, holidays: dict[date, str]) -> dict:
    """Day-by-day explanation, used by the API so the copilot can cite *why*."""
    days = []
    for d in iter_days(start, end):
        if d.weekday() >= 5:
            kind, note = "weekend", None
        elif d in holidays:
            kind, note = "holiday", holidays[d]
        else:
            kind, note = "working_day", None
        days.append({"date": d.isoformat(), "weekday": d.strftime("%a"), "type": kind, "holiday_name": note})
    return {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "calendar_days": len(days),
        "working_days": sum(1 for x in days if x["type"] == "working_day"),
        "days": days,
    }


def add_working_days(start: date, n: int, holidays: set[date]) -> date:
    """The n-th working day after `start` (used for notice-period checks)."""
    d, left = start, n
    while left > 0:
        d += timedelta(days=1)
        if is_working_day(d, holidays):
            left -= 1
    return d
