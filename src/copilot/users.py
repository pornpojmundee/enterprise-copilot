"""Who is asking. Until SSO arrives (week 5) the user is picked by employee ID."""
from __future__ import annotations

from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

from .config import postgres_dsn


@dataclass(frozen=True)
class User:
    employee_id: str
    name: str
    app_role: str
    team_id: str | None
    dept_id: str


def get_user(employee_id: str) -> User:
    with psycopg.connect(postgres_dsn(), row_factory=dict_row) as conn:
        r = conn.execute(
            "SELECT employee_id, first_name_th || ' ' || last_name_th AS name, app_role, team_id, dept_id, "
            "employment_status FROM hris.employees WHERE employee_id = %s",
            (employee_id,),
        ).fetchone()
    if r is None or r["employment_status"] == "resigned":
        raise LookupError(f"no active employee {employee_id}")
    return User(r["employee_id"], r["name"], r["app_role"], r["team_id"], r["dept_id"])
