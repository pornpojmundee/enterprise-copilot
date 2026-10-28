"""Working-day calculation for leave questions (UC1), using the company holiday calendar.

LLMs are unreliable at "which weekday is 4 Dec 2026, and is the 7th a holiday?" —
so the router only extracts the dates and this code does the counting (HR-001 §4 rules).
"""
from __future__ import annotations

from datetime import date

import psycopg

from copilot.config import postgres_dsn
from mock_hris.workdays import breakdown, count_working_days

TH_WEEKDAY = {"Mon": "จันทร์", "Tue": "อังคาร", "Wed": "พุธ", "Thu": "พฤหัสบดี", "Fri": "ศุกร์", "Sat": "เสาร์", "Sun": "อาทิตย์"}


def working_days_report(start: date, end: date, half_day: str | None = None) -> dict:
    if end < start:
        start, end = end, start
    if (end - start).days > 60:
        raise ValueError("date range longer than 60 days")
    with psycopg.connect(postgres_dsn()) as conn:
        rows = conn.execute("SELECT holiday_date, name_th FROM hris.holidays WHERE holiday_date BETWEEN %s AND %s",
                            (start, end)).fetchall()
    holidays = {d: n for d, n in rows}
    days = count_working_days(start, end, set(holidays), half_day if start == end else None)
    detail = breakdown(start, end, holidays)
    lines = []
    for d in detail["days"]:
        label = {"working_day": "วันทำงาน — นับเป็นวันลา", "weekend": "วันหยุดสุดสัปดาห์ — ไม่นับ",
                 "holiday": f"{d['holiday_name']} — ไม่นับ"}[d["type"]]
        lines.append(f"{d['date']} ({TH_WEEKDAY[d['weekday']]}): {label}")
    return {"start": start.isoformat(), "end": end.isoformat(), "leave_days": days, "lines": lines,
            "text": f"ช่วง {start.isoformat()} ถึง {end.isoformat()} นับเป็นวันลา {days:g} วันทำงาน (ตาม HR-001 §4)\n" + "\n".join(lines)}
