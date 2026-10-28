"""NawaHR mock API.

Run:  uvicorn mock_hris.main:app --app-dir src --port 8001 --reload
Docs: http://localhost:8001/docs
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal

import psycopg
from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from .auth import FULL_HR_ACCESS, Actor, get_actor, require_view
from .db import get_conn, holidays_between, today
from .workdays import add_working_days, breakdown, count_working_days

app = FastAPI(
    title="NawaHR (mock HRIS)",
    version="0.1.0",
    description="Mock HR system of the fictional company Nawa Tech. Every call needs "
    "`X-API-Key` (service key) and `X-Acting-Employee-Id` (the user the copilot acts for).",
)

EMPLOYEE_PUBLIC_COLS = (
    "employee_id, first_name_th, last_name_th, first_name_en, last_name_en, nickname, email, "
    "dept_id, team_id, position, level, manager_id, app_role, location, hire_date, "
    "probation_end_date, employment_status"
)  # never compensation


# --------------------------------------------------------------------------- models
class LeaveRequestIn(BaseModel):
    leave_type: Literal["VAC", "SICK", "PER"]
    start_date: date
    end_date: date
    half_day: Literal["am", "pm"] | None = None
    reason: str = Field(default="", max_length=500)
    dry_run: bool = Field(default=False, description="Validate and preview only; nothing is saved")

    @model_validator(mode="after")
    def _dates(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date is before start_date")
        if self.half_day and self.start_date != self.end_date:
            raise ValueError("half-day leave must be a single date")
        if self.start_date.year != self.end_date.year:
            raise ValueError("leave across two calendar years must be split into two requests")
        return self


class Violation(BaseModel):
    code: str
    message_th: str
    policy_ref: str


class LeaveRequestPreview(BaseModel):
    valid: bool
    working_days: float
    balance_before: float | None
    balance_after: float | None
    violations: list[Violation]
    warnings: list[Violation]
    calendar: dict
    request_id: str | None = None
    status: str | None = None


# --------------------------------------------------------------------------- helpers
def _num(x) -> float:
    return float(x) if isinstance(x, Decimal) else x


def _clean(row: dict) -> dict:
    return {k: _num(v) for k, v in row.items()}


def _balance(conn, employee_id: str, year: int, leave_type: str) -> dict | None:
    row = conn.execute(
        "SELECT entitled, carried_over, used, pending FROM hris.leave_balances "
        "WHERE employee_id = %s AND year = %s AND leave_type = %s",
        (employee_id, year, leave_type),
    ).fetchone()
    if row is None:
        return None
    b = _clean(row)
    b["remaining"] = b["entitled"] + b["carried_over"] - b["used"] - b["pending"]
    return b


# --------------------------------------------------------------------------- routes
@app.get("/health", tags=["meta"])
def health(conn: psycopg.Connection = Depends(get_conn)):
    conn.execute("SELECT 1")
    return {"status": "ok", "today": today().isoformat()}


@app.get("/me", tags=["employees"])
def me(actor: Actor = Depends(get_actor), conn: psycopg.Connection = Depends(get_conn)):
    return get_employee(actor.employee_id, actor, conn)


@app.get("/employees/{employee_id}", tags=["employees"])
def get_employee(employee_id: str, actor: Actor = Depends(get_actor), conn: psycopg.Connection = Depends(get_conn)):
    require_view(conn, actor, employee_id)
    row = conn.execute(
        f"""SELECT {EMPLOYEE_PUBLIC_COLS},
                   (SELECT first_name_en || ' ' || last_name_en FROM hris.employees m
                     WHERE m.employee_id = e.manager_id) AS manager_name
            FROM hris.employees e WHERE employee_id = %s""",
        (employee_id,),
    ).fetchone()
    return row


@app.get("/employees/{employee_id}/leave-balances", tags=["leave"])
def leave_balances(
    employee_id: str,
    year: int | None = None,
    actor: Actor = Depends(get_actor),
    conn: psycopg.Connection = Depends(get_conn),
):
    require_view(conn, actor, employee_id)
    year = year or today().year
    rows = conn.execute(
        """SELECT b.leave_type, t.name_th, t.name_en, b.entitled, b.carried_over, b.used, b.pending,
                  b.entitled + b.carried_over - b.used - b.pending AS remaining
           FROM hris.leave_balances b JOIN hris.leave_types t ON t.code = b.leave_type
           WHERE b.employee_id = %s AND b.year = %s ORDER BY b.leave_type DESC""",
        (employee_id, year),
    ).fetchall()
    return {
        "employee_id": employee_id,
        "year": year,
        "note": "remaining = entitled + carried_over - used - pending; counted in working days (HR-001 §4)",
        "balances": [_clean(r) for r in rows],
    }


@app.get("/employees/{employee_id}/leave-requests", tags=["leave"])
def leave_requests(
    employee_id: str,
    year: int | None = None,
    status_: str | None = Query(default=None, alias="status"),
    actor: Actor = Depends(get_actor),
    conn: psycopg.Connection = Depends(get_conn),
):
    require_view(conn, actor, employee_id)
    year = year or today().year
    sql = ("SELECT request_id, leave_type, start_date, end_date, half_day, working_days, status, reason, "
           "approver_id, created_at FROM hris.leave_requests WHERE employee_id = %s "
           "AND extract(year FROM start_date) = %s")
    params: list = [employee_id, year]
    if status_:
        sql += " AND status = %s"
        params.append(status_)
    rows = conn.execute(sql + " ORDER BY start_date", params).fetchall()
    return {"employee_id": employee_id, "year": year, "requests": [_clean(r) for r in rows]}


@app.get("/holidays", tags=["calendar"])
def holidays(year: int | None = None, actor: Actor = Depends(get_actor), conn: psycopg.Connection = Depends(get_conn)):
    year = year or today().year
    rows = conn.execute(
        "SELECT holiday_date, name_th, name_en, is_substitute FROM hris.holidays "
        "WHERE extract(year FROM holiday_date) = %s ORDER BY holiday_date",
        (year,),
    ).fetchall()
    return {"year": year, "policy_ref": "HR-002", "holidays": rows}


@app.get("/calendar/working-days", tags=["calendar"])
def working_days(
    start: date,
    end: date,
    half_day: Literal["am", "pm"] | None = None,
    actor: Actor = Depends(get_actor),
    conn: psycopg.Connection = Depends(get_conn),
):
    """How many leave days a date range costs, with a per-day explanation (weekend / holiday)."""
    if end < start:
        raise HTTPException(422, "end is before start")
    if (end - start).days > 366:
        raise HTTPException(422, "range longer than one year")
    hol = holidays_between(conn, start, end)
    try:
        wd = count_working_days(start, end, set(hol), half_day)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    result = breakdown(start, end, hol)
    result["leave_days_deducted"] = wd
    result["policy_ref"] = "HR-001 §4"
    return result


@app.post("/leave-requests", response_model=LeaveRequestPreview, tags=["leave"])
def create_leave_request(
    body: LeaveRequestIn,
    actor: Actor = Depends(get_actor),
    conn: psycopg.Connection = Depends(get_conn),
):
    """Submit (or preview with dry_run=true) a leave request for the acting employee.

    Employees can only file leave for themselves — the copilot cannot file on someone's behalf.
    """
    emp = conn.execute(
        "SELECT employee_id, manager_id, probation_end_date, employment_status FROM hris.employees "
        "WHERE employee_id = %s",
        (actor.employee_id,),
    ).fetchone()
    t = today()
    hol = holidays_between(conn, body.start_date, body.end_date)
    wd = count_working_days(body.start_date, body.end_date, set(hol), body.half_day)
    violations: list[Violation] = []
    warnings: list[Violation] = []

    if wd == 0:
        violations.append(Violation(code="NO_WORKING_DAYS", policy_ref="HR-001 §4",
                                    message_th="ช่วงที่เลือกไม่มีวันทำงาน (เป็นวันหยุดทั้งหมด) จึงไม่ต้องยื่นลา"))
    if body.leave_type == "VAC" and emp["probation_end_date"] >= body.start_date:
        violations.append(Violation(code="PROBATION_NO_VAC", policy_ref="HR-001 §2",
                                    message_th="อยู่ระหว่างทดลองงาน ยังไม่มีสิทธิ์ลาพักร้อน"))

    bal = _balance(conn, actor.employee_id, body.start_date.year, body.leave_type)
    before = bal["remaining"] if bal else None
    if bal is None:
        violations.append(Violation(code="NO_BALANCE_RECORD", policy_ref="HR-001 §3",
                                    message_th="ไม่พบสิทธิ์วันลาของปีนี้ในระบบ กรุณาติดต่อ HR"))
    elif wd > bal["remaining"]:
        violations.append(Violation(code="INSUFFICIENT_BALANCE", policy_ref="HR-001 §3",
                                    message_th=f"วันลาคงเหลือ {bal['remaining']:g} วัน ไม่พอสำหรับ {wd:g} วัน"))

    overlap = conn.execute(
        "SELECT request_id FROM hris.leave_requests WHERE employee_id = %s AND status IN ('pending','approved') "
        "AND start_date <= %s AND end_date >= %s",
        (actor.employee_id, body.end_date, body.start_date),
    ).fetchone()
    if overlap:
        violations.append(Violation(code="OVERLAP", policy_ref="HR-001 §5",
                                    message_th=f"ช่วงวันที่ซ้อนกับใบลา {overlap['request_id']} ที่มีอยู่แล้ว"))

    # Notice period — a warning, not a block: the manager decides (HR-001 §3.1, §3.3)
    if body.leave_type == "VAC":
        need = 7 if wd >= 3 else 3
        all_hol = set(holidays_between(conn, t, body.start_date))
        if body.start_date < add_working_days(t, need, all_hol):
            warnings.append(Violation(code="SHORT_NOTICE", policy_ref="HR-001 §3.1",
                                      message_th=f"ลาพักร้อน {wd:g} วัน ควรยื่นล่วงหน้าอย่างน้อย {need} วันทำงาน"))
    if body.leave_type == "SICK" and wd >= 3:
        warnings.append(Violation(code="MEDICAL_CERT_REQUIRED", policy_ref="HR-001 §3.2",
                                  message_th="ลาป่วยตั้งแต่ 3 วันทำงานขึ้นไป ต้องแนบใบรับรองแพทย์ใน NawaHR"))
    if body.leave_type == "SICK" and body.start_date > t:
        warnings.append(Violation(code="SICK_IN_FUTURE", policy_ref="HR-001 §3.2",
                                  message_th="ลาป่วยล่วงหน้าใช้ได้เฉพาะกรณีนัดแพทย์ล่วงหน้า"))

    preview = LeaveRequestPreview(
        valid=not violations, working_days=wd, balance_before=before,
        balance_after=(before - wd) if before is not None else None,
        violations=violations, warnings=warnings, calendar=breakdown(body.start_date, body.end_date, hol),
    )
    if body.dry_run:
        return preview
    if violations:
        raise HTTPException(422, preview.model_dump(mode="json"))

    conn.execute("SELECT pg_advisory_xact_lock(hashtext('hris.leave_requests'))")
    prefix = f"LV-{body.start_date.year}-"
    last = conn.execute(
        "SELECT max(request_id) AS m FROM hris.leave_requests WHERE request_id LIKE %s", (prefix + "%",)
    ).fetchone()["m"]
    req_id = f"{prefix}{(int(last.rsplit('-', 1)[1]) + 1) if last else 1:05d}"
    conn.execute(
        "INSERT INTO hris.leave_requests (request_id, employee_id, leave_type, start_date, end_date, half_day, "
        "working_days, status, reason, approver_id, created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s)",
        (req_id, actor.employee_id, body.leave_type, body.start_date, body.end_date, body.half_day, wd,
         body.reason, emp["manager_id"], datetime.now(timezone.utc)),
    )
    conn.execute(
        "UPDATE hris.leave_balances SET pending = pending + %s WHERE employee_id = %s AND year = %s AND leave_type = %s",
        (wd, actor.employee_id, body.start_date.year, body.leave_type),
    )
    preview.request_id, preview.status = req_id, "pending"
    return preview


@app.post("/leave-requests/{request_id}/cancel", tags=["leave"])
def cancel_leave_request(request_id: str, actor: Actor = Depends(get_actor), conn: psycopg.Connection = Depends(get_conn)):
    """Cancel your own pending/approved request before it starts (HR-001 §5)."""
    r = conn.execute("SELECT * FROM hris.leave_requests WHERE request_id = %s FOR UPDATE", (request_id,)).fetchone()
    if r is None or r["employee_id"] != actor.employee_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "leave request not found")
    if r["status"] not in ("pending", "approved"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"request is already {r['status']}")
    if r["start_date"] <= today():
        raise HTTPException(status.HTTP_409_CONFLICT, "leave has already started — contact HR Operations (HR-001 §5)")
    col = "pending" if r["status"] == "pending" else "used"
    conn.execute("UPDATE hris.leave_requests SET status = 'cancelled' WHERE request_id = %s", (request_id,))
    conn.execute(
        f"UPDATE hris.leave_balances SET {col} = {col} - %s WHERE employee_id = %s AND year = %s AND leave_type = %s",
        (r["working_days"], r["employee_id"], r["start_date"].year, r["leave_type"]),
    )
    return {"request_id": request_id, "status": "cancelled", "days_returned": _num(r["working_days"])}


@app.get("/teams/{team_id}/members", tags=["employees"])
def team_members(team_id: str, actor: Actor = Depends(get_actor), conn: psycopg.Connection = Depends(get_conn)):
    """Team roster with leave summary — for the team's lead, its department head, HR and executives."""
    team = conn.execute(
        "SELECT t.team_id, t.name_en, t.lead_employee_id, d.head_employee_id FROM hris.teams t "
        "JOIN hris.departments d USING (dept_id) WHERE t.team_id = %s",
        (team_id,),
    ).fetchone()
    allowed = team and (actor.app_role in FULL_HR_ACCESS
                        or actor.employee_id in (team["lead_employee_id"], team["head_employee_id"]))
    if not allowed:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "team not found")
    rows = conn.execute(
        """SELECT e.employee_id, e.first_name_en, e.last_name_en, e.nickname, e.position, e.employment_status,
                  b.entitled + b.carried_over - b.used - b.pending AS vac_remaining
           FROM hris.employees e
           LEFT JOIN hris.leave_balances b ON b.employee_id = e.employee_id AND b.year = %s AND b.leave_type = 'VAC'
           WHERE e.team_id = %s AND e.employment_status <> 'resigned' ORDER BY e.employee_id""",
        (today().year, team_id),
    ).fetchall()
    return {"team_id": team_id, "name": team["name_en"], "members": [_clean(r) for r in rows]}
