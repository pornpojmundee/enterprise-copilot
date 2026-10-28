"""Run a checked query as the asking user: read-only role, read-only transaction,
statement timeout, and the user context that row-level security filters on."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import psycopg

from copilot.config import postgres_dsn
from copilot.users import User

MAX_ROWS = 200


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[tuple]
    truncated: bool

    def as_table(self, max_rows: int = 50) -> str:
        """Compact pipe table for the LLM (and humans)."""
        def fmt(v):
            if v is None:
                return ""
            if isinstance(v, Decimal):
                return f"{v.normalize():f}"
            if isinstance(v, datetime):
                return v.strftime("%Y-%m-%d %H:%M")
            if isinstance(v, date):
                return v.isoformat()
            return str(v).replace("\n", " ")[:200]
        lines = [" | ".join(self.columns)]
        lines += [" | ".join(fmt(v) for v in r) for r in self.rows[:max_rows]]
        if len(self.rows) > max_rows or self.truncated:
            lines.append(f"... ({len(self.rows)}{'+' if self.truncated else ''} rows total)")
        return "\n".join(lines)


def run_as_user(sql: str, user: User, params: tuple = ()) -> QueryResult:
    timeout_ms = int(os.getenv("DATA_QUERY_TIMEOUT_MS", "5000"))
    with psycopg.connect(postgres_dsn(), autocommit=False) as conn:
        try:
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SET LOCAL ROLE copilot_reader")
            conn.execute(f"SET LOCAL statement_timeout = {timeout_ms}")
            conn.execute("SET LOCAL search_path = copilot_data")
            conn.execute(
                "SELECT set_config('app.user_id', %s, true), set_config('app.role', %s, true)",
                (user.employee_id, user.app_role),
            )
            cur = conn.execute(sql, params or None)
            columns = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchmany(MAX_ROWS + 1)
            return QueryResult(columns, [tuple(r) for r in rows[:MAX_ROWS]], truncated=len(rows) > MAX_ROWS)
        finally:
            conn.rollback()
