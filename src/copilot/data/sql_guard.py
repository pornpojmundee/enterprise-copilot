"""Static checks on LLM-generated SQL before it touches the database.

This is the second of three layers (semantic layer -> SQL guard -> row-level security).
Even if this check missed something, the read-only role and RLS still hold — but rejecting
bad SQL early gives the LLM a clear error to fix and keeps the audit log clean.

Rules:
  * exactly one statement, and it must be a query (SELECT / WITH ... SELECT / UNION)
  * only views in schema copilot_data (or CTEs defined in the same query)
  * no row locks (FOR UPDATE), no SELECT INTO
  * functions: any standard SQL function sqlglot recognizes, plus a small allowlist of
    Postgres-specific ones. Everything else is rejected — notably set_config() and
    current_setting(), which could otherwise rewrite the per-request user context that
    row-level security relies on, and pg_sleep / pg_read_file / dblink style functions.
  * a LIMIT is added when missing
"""
from __future__ import annotations

from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

SCHEMA = "copilot_data"
ALLOWED_VIEWS = {
    "employees", "teams", "departments", "holidays", "leave_balances", "leave_requests",
    "tickets", "ticket_comments", "sla_policies",
}
# Postgres functions sqlglot does not model as typed expressions, that are safe to allow.
ALLOWED_ANONYMOUS = {"age", "date_part", "greatest", "least", "to_char", "make_date", "justify_interval", "initcap"}
DEFAULT_LIMIT = 200
FORBIDDEN_NODES = (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
                   exp.Command, exp.Into, exp.Lock, exp.Set, exp.Copy, exp.TruncateTable)


class UnsafeSQL(ValueError):
    """Raised with a message meant to be shown back to the LLM so it can fix the query."""


@dataclass
class CheckedSQL:
    sql: str
    tables: list[str]


def check_sql(sql: str, limit: int = DEFAULT_LIMIT) -> CheckedSQL:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        raise UnsafeSQL("empty query")
    try:
        statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
    except ParseError as e:
        raise UnsafeSQL(f"could not parse SQL: {str(e).splitlines()[0]}") from e
    if len(statements) != 1:
        raise UnsafeSQL("exactly one statement is allowed")
    tree = statements[0]
    if not isinstance(tree, exp.Query):
        raise UnsafeSQL(f"only SELECT queries are allowed (got {tree.key.upper()})")
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise UnsafeSQL(f"{node.key.upper()} is not allowed")

    cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    tables = []
    for t in tree.find_all(exp.Table):
        name, db = t.name.lower(), (t.db or "").lower()
        if not db and name in cte_names:
            continue
        if db not in ("", SCHEMA) or t.catalog:
            raise UnsafeSQL(f"table {t.sql()} is not allowed — use views in schema {SCHEMA}")
        if name not in ALLOWED_VIEWS:
            raise UnsafeSQL(f"unknown view {name!r}; allowed: {', '.join(sorted(ALLOWED_VIEWS))}")
        t.set("db", exp.to_identifier(SCHEMA))  # always fully qualified
        tables.append(name)

    for f in tree.find_all(exp.Func):
        if isinstance(f, exp.Anonymous) and f.name.lower() not in ALLOWED_ANONYMOUS:
            raise UnsafeSQL(f"function {f.name}() is not allowed")

    if isinstance(tree, exp.Select) and not tree.args.get("limit"):
        tree = tree.limit(limit)
    elif isinstance(tree, exp.SetOperation) and not tree.args.get("limit"):
        tree = exp.select("*").from_(tree.subquery("q")).limit(limit)
    return CheckedSQL(sql=tree.sql(dialect="postgres"), tables=sorted(set(tables)))
