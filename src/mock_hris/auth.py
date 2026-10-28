"""Authentication and authorization for the mock HRIS.

Two headers, mirroring how an enterprise copilot usually talks to a system of record:
  X-API-Key            — the copilot's *service* credential (proves the caller is the copilot)
  X-Acting-Employee-Id — the end user the copilot is acting for (from SSO in week 5)

The HRIS enforces data access itself, so even a buggy or prompt-injected agent cannot read
someone else's leave data: it only ever gets what the acting user could see in NawaHR.
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass

import psycopg
from fastapi import Depends, Header, HTTPException, status

from .db import get_conn

DEFAULT_DEV_KEY = "dev-hris-key-change-me"
FULL_HR_ACCESS = {"hr", "executive"}


@dataclass(frozen=True)
class Actor:
    employee_id: str
    app_role: str
    team_id: str | None
    dept_id: str


def _expected_key() -> str:
    return os.getenv("HRIS_API_KEY", DEFAULT_DEV_KEY)


def get_actor(
    x_api_key: str = Header(..., alias="X-API-Key"),
    x_acting_employee_id: str = Header(..., alias="X-Acting-Employee-Id"),
    conn: psycopg.Connection = Depends(get_conn),
) -> Actor:
    if not secrets.compare_digest(x_api_key, _expected_key()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")
    row = conn.execute(
        "SELECT employee_id, app_role, team_id, dept_id, employment_status "
        "FROM hris.employees WHERE employee_id = %s",
        (x_acting_employee_id,),
    ).fetchone()
    if row is None or row["employment_status"] == "resigned":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "acting employee is unknown or inactive")
    return Actor(row["employee_id"], row["app_role"], row["team_id"], row["dept_id"])


def can_view_employee(conn: psycopg.Connection, actor: Actor, target_id: str) -> bool:
    """Self, anyone in the actor's reporting line (direct or indirect), or HR/executives."""
    if actor.employee_id == target_id or actor.app_role in FULL_HR_ACCESS:
        return True
    row = conn.execute(
        """
        WITH RECURSIVE reports AS (
            SELECT employee_id FROM hris.employees WHERE manager_id = %(me)s
            UNION
            SELECT e.employee_id FROM hris.employees e JOIN reports r ON e.manager_id = r.employee_id
        )
        SELECT 1 FROM reports WHERE employee_id = %(target)s
        """,
        {"me": actor.employee_id, "target": target_id},
    ).fetchone()
    return row is not None


def require_view(conn: psycopg.Connection, actor: Actor, target_id: str) -> None:
    exists = conn.execute("SELECT 1 FROM hris.employees WHERE employee_id = %s", (target_id,)).fetchone()
    # Same 404 for "doesn't exist" and "not allowed" so callers can't probe for employee IDs.
    if exists is None or not can_view_employee(conn, actor, target_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "employee not found")
