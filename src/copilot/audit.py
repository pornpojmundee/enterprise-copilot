"""Audit log writer: who asked what, which agents/data were used, and what was done.

Writes to copilot_sec.audit_log (append-only, see db/init/005_security.sql). Best effort: a
failure to write the audit row is printed but never breaks the user's conversation.
Only already-masked text should be passed in (the orchestrator masks PII first).
"""
from __future__ import annotations

import json
import sys
from typing import Any

import psycopg

from .config import postgres_dsn

COLUMNS = ("event", "employee_id", "app_role", "thread_id", "question", "agents", "sources", "sql_text",
           "tool", "guardrail", "pii_types", "outcome", "llm_calls", "cost_usd", "latency_ms", "detail")


def record(event: str, **fields: Any) -> None:
    row = {"event": event, **{k: v for k, v in fields.items() if k in COLUMNS}}
    if isinstance(row.get("detail"), dict):
        row["detail"] = json.dumps(row["detail"], ensure_ascii=False, default=str)
    cols = list(row)
    try:
        with psycopg.connect(postgres_dsn(), connect_timeout=3) as conn:
            conn.execute(f"INSERT INTO copilot_sec.audit_log ({', '.join(cols)}) "
                         f"VALUES ({', '.join(['%s'] * len(cols))})", [row[c] for c in cols])
    except Exception as e:  # noqa: BLE001 — auditing must not take the chat down
        print(f"[audit] could not write {event} event: {e}", file=sys.stderr)


def recent(limit: int = 100) -> list[dict]:
    """Latest audit rows, for the admin view."""
    with psycopg.connect(postgres_dsn()) as conn:
        cur = conn.execute(
            "SELECT ts, event, employee_id, app_role, question, agents, guardrail, pii_types, outcome, "
            "tool, llm_calls, cost_usd, sql_text FROM copilot_sec.audit_log ORDER BY id DESC LIMIT %s", (limit,))
        names = [d.name for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]


def summary_today() -> dict:
    with psycopg.connect(postgres_dsn()) as conn:
        r = conn.execute("""
            SELECT count(*) FILTER (WHERE event = 'ask'),
                   count(DISTINCT employee_id) FILTER (WHERE event = 'ask'),
                   count(*) FILTER (WHERE guardrail IS NOT NULL),
                   count(*) FILTER (WHERE cardinality(pii_types) > 0),
                   count(*) FILTER (WHERE event = 'login_failed'),
                   coalesce(sum(cost_usd), 0)
            FROM copilot_sec.audit_log WHERE ts >= date_trunc('day', now())""").fetchone()
    keys = ("questions", "users", "blocked", "pii_masked", "failed_logins", "cost_usd")
    return dict(zip(keys, r))
