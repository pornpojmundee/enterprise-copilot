"""Ticket operations with authorization. Pure Python — the MCP server is a thin wrapper.

Reads go through the same read-only, row-level-security path as the Data agent, so a user can
only ever see tickets they could see in NawaDesk. Writes check permissions explicitly:
  * anyone can open a ticket for themselves and comment on tickets they can see
  * only support staff of the right queue may change status (security test SEC5)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from copilot.config import postgres_dsn
from copilot.data.executor import run_as_user
from copilot.users import User

SUBCATEGORIES = {
    "it": {"hardware-notebook", "hardware-peripheral", "account-password", "network-vpn", "email-outlook",
           "software-request", "access-request", "security-phishing"},
    "hr": {"payroll", "leave-correction", "document-request", "benefits"},
}
INFRA_SUBCATEGORIES = {"network-vpn", "access-request", "security-phishing"}
PRIORITIES = {"P1", "P2", "P3", "P4"}
STATUSES = {"open", "in_progress", "waiting", "resolved", "closed"}
STAFF_ROLE_FOR_CATEGORY = {"it": {"it_support", "admin"}, "hr": {"hr"}}


class TicketError(ValueError):
    """Invalid input — message is safe to show to the user / model."""


class TicketPermissionError(PermissionError):
    """The acting user may not do this — message is safe to show."""


def _rows_to_dicts(result) -> list[dict]:
    out = []
    for r in result.rows:
        d = {}
        for k, v in zip(result.columns, r):
            d[k] = v.isoformat() if isinstance(v, datetime) else v
        out.append(d)
    return out


class TicketService:
    def __init__(self, user: User):
        self.user = user

    # ---------- reads (row-level security) ----------
    def get_ticket(self, ticket_id: str) -> dict:
        res = run_as_user(
            "SELECT ticket_id, category, subcategory, title, description, requester_id, assigned_team_id, "
            "assignee_id, priority, status, created_at, sla_due_at, sla_breached, resolution "
            "FROM copilot_data.tickets WHERE ticket_id = %s", self.user, (ticket_id.upper(),))
        rows = _rows_to_dicts(res)
        if not rows:  # same message whether missing or not visible
            raise TicketError(f"ticket {ticket_id} not found")
        ticket = rows[0]
        comments = run_as_user(
            "SELECT author_id, body, created_at FROM copilot_data.ticket_comments WHERE ticket_id = %s "
            "ORDER BY created_at", self.user, (ticket["ticket_id"],))
        ticket["comments"] = _rows_to_dicts(comments)
        return ticket

    def list_my_tickets(self, only_open: bool = True) -> list[dict]:
        sql = ("SELECT ticket_id, title, priority, status, created_at, sla_breached FROM copilot_data.tickets "
               "WHERE requester_id = %s" + (" AND is_open" if only_open else "") + " ORDER BY created_at DESC LIMIT 20")
        return _rows_to_dicts(run_as_user(sql, self.user, (self.user.employee_id,)))

    # ---------- writes (explicit authorization) ----------
    def create_ticket(self, title: str, description: str, category: str, subcategory: str, priority: str) -> dict:
        category, subcategory, priority = category.lower(), subcategory.lower(), priority.upper()
        if category not in SUBCATEGORIES:
            raise TicketError("category must be 'it' or 'hr'")
        if subcategory not in SUBCATEGORIES[category]:
            raise TicketError(f"subcategory for {category} must be one of {sorted(SUBCATEGORIES[category])}")
        if priority not in PRIORITIES:
            raise TicketError("priority must be P1, P2, P3 or P4")
        title, description = title.strip(), description.strip()
        if not (3 <= len(title) <= 120) or not description:
            raise TicketError("title (3-120 chars) and description are required")
        team = ("IT-INF" if subcategory in INFRA_SUBCATEGORIES else "IT-SD") if category == "it" else \
               ("HR-TAL" if subcategory == "benefits" else "HR-OPS")
        prefix = "IT" if category == "it" else "HR"
        now = datetime.now(timezone.utc)
        with psycopg.connect(postgres_dsn(), row_factory=dict_row) as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtext('itsm.tickets.id'))")
            hours = conn.execute("SELECT resolve_hours FROM itsm.sla_policies WHERE priority = %s",
                                 (priority,)).fetchone()["resolve_hours"]
            last = conn.execute(
                "SELECT max(substring(ticket_id from 4)::int) AS n FROM itsm.tickets WHERE ticket_id LIKE %s",
                (prefix + "-%",)).fetchone()["n"] or 0
            ticket_id = f"{prefix}-{last + 1:04d}"
            conn.execute(
                "INSERT INTO itsm.tickets (ticket_id, category, subcategory, title, description, requester_id, "
                "requester_team_id, assigned_team_id, priority, status, created_at, sla_due_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',%s,%s)",
                (ticket_id, category, subcategory, title, description, self.user.employee_id, self.user.team_id,
                 team, priority, now, now + timedelta(hours=float(hours))))
        return {"ticket_id": ticket_id, "status": "open", "priority": priority, "assigned_team_id": team,
                "sla_due_at": (now + timedelta(hours=float(hours))).isoformat()}

    def add_comment(self, ticket_id: str, body: str) -> dict:
        ticket = self.get_ticket(ticket_id)  # raises if not visible
        if ticket["status"] == "closed":
            raise TicketError(f"{ticket['ticket_id']} is closed — open a new ticket instead")
        if not body.strip():
            raise TicketError("comment is empty")
        with psycopg.connect(postgres_dsn()) as conn:
            conn.execute("INSERT INTO itsm.ticket_comments (ticket_id, author_id, body) VALUES (%s,%s,%s)",
                         (ticket["ticket_id"], self.user.employee_id, body.strip()))
        return {"ticket_id": ticket["ticket_id"], "comment_added": True}

    def update_status(self, ticket_id: str, status: str, resolution: str = "") -> dict:
        status = status.lower()
        if status not in STATUSES:
            raise TicketError(f"status must be one of {sorted(STATUSES)}")
        ticket = self.get_ticket(ticket_id)
        if self.user.app_role not in STAFF_ROLE_FOR_CATEGORY[ticket["category"]]:
            raise TicketPermissionError(
                "only the support team can change a ticket's status (IT-001 §4) — "
                "you can add a comment or ask the support team instead")
        if status in ("resolved", "closed") and not (resolution.strip() or ticket.get("resolution")):
            raise TicketError("a resolution note is required to resolve or close a ticket")
        with psycopg.connect(postgres_dsn()) as conn:
            conn.execute(
                "UPDATE itsm.tickets SET status = %s, resolution = COALESCE(NULLIF(%s, ''), resolution), "
                "resolved_at = CASE WHEN %s IN ('resolved','closed') THEN COALESCE(resolved_at, now()) ELSE NULL END, "
                "assignee_id = COALESCE(assignee_id, %s), first_response_at = COALESCE(first_response_at, now()) "
                "WHERE ticket_id = %s",
                (status, resolution.strip(), status, self.user.employee_id, ticket["ticket_id"]))
        return {"ticket_id": ticket["ticket_id"], "status": status}
