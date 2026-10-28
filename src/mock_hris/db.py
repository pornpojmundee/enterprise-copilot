"""Database helpers for the mock HRIS."""
from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date

import psycopg
from psycopg.rows import dict_row

from copilot.config import postgres_dsn


def get_conn() -> Iterator[psycopg.Connection]:
    """FastAPI dependency: one connection per request, committed on success."""
    with psycopg.connect(postgres_dsn(), row_factory=dict_row) as conn:
        yield conn


def today() -> date:
    """'Today' for business rules. HRIS_TODAY pins it (tests, demos); default is the real date."""
    pinned = os.getenv("HRIS_TODAY")
    return date.fromisoformat(pinned) if pinned else date.today()


def holidays_between(conn: psycopg.Connection, start: date, end: date) -> dict[date, str]:
    rows = conn.execute(
        "SELECT holiday_date, name_th FROM hris.holidays WHERE holiday_date BETWEEN %s AND %s",
        (start, end),
    ).fetchall()
    return {r["holiday_date"]: r["name_th"] for r in rows}
