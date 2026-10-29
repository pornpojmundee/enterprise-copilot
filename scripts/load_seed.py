"""Load data/seed/*.csv into Postgres (re-runnable: wipes and reloads the mock data).

    python scripts/load_seed.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from copilot.config import postgres_dsn  # noqa: E402

SEED = ROOT / "data" / "seed"
SCHEMA_SQL = ROOT / "db" / "init" / "002_schema.sql"
SECURITY_SQL = ROOT / "db" / "init" / "004_copilot_data.sql"   # views, read-only role, row-level security
AUTH_AUDIT_SQL = ROOT / "db" / "init" / "005_security.sql"    # sign-in credentials + audit log

# Parent tables first. employees has a self-reference (manager_id) and departments/teams
# point at employees, so FK checks are deferred by loading inside one transaction with
# session_replication_role = replica (dev-only shortcut; we validate FKs afterwards).
TABLES = [
    ("hris.departments", "departments.csv"),
    ("hris.teams", "teams.csv"),
    ("hris.employees", "employees.csv"),
    ("hris.compensation", "compensation.csv"),
    ("hris.leave_types", "leave_types.csv"),
    ("hris.holidays", "holidays.csv"),
    ("hris.leave_balances", "leave_balances.csv"),
    ("hris.leave_requests", "leave_requests.csv"),
    ("itsm.sla_policies", "sla_policies.csv"),
    ("itsm.tickets", "tickets.csv"),
]

FK_CHECKS = {
    "employee manager exists": "SELECT count(*) FROM hris.employees e WHERE manager_id IS NOT NULL "
                               "AND NOT EXISTS (SELECT 1 FROM hris.employees m WHERE m.employee_id = e.manager_id)",
    "team lead exists": "SELECT count(*) FROM hris.teams t WHERE NOT EXISTS "
                        "(SELECT 1 FROM hris.employees e WHERE e.employee_id = t.lead_employee_id)",
    "ticket requester exists": "SELECT count(*) FROM itsm.tickets t WHERE NOT EXISTS "
                               "(SELECT 1 FROM hris.employees e WHERE e.employee_id = t.requester_id)",
}


def main() -> int:
    try:
        return _load()
    except psycopg.errors.LockNotAvailable:
        print("\nAnother connection is holding a lock on the tables (e.g. uvicorn, a DB client, or a stuck script).\n"
              "Stop it, or run:  docker compose restart db   then run this script again.")
        return 1


def _load() -> int:
    with psycopg.connect(postgres_dsn()) as conn:
        # Fail fast instead of hanging if another session (API server, DB tool, stuck script) holds a lock.
        conn.execute("SET lock_timeout = '10s'")
        print("Applying schema, views and row-level security...", flush=True)
        conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))
        conn.execute(SECURITY_SQL.read_text(encoding="utf-8"))
        conn.execute(AUTH_AUDIT_SQL.read_text(encoding="utf-8"))
        conn.execute("TRUNCATE " + ", ".join(t for t, _ in TABLES) + ", itsm.ticket_comments CASCADE")
        conn.execute("SET session_replication_role = replica")
        for table, fname in TABLES:
            path = SEED / fname
            header = path.read_text(encoding="utf-8").splitlines()[0]
            with conn.cursor().copy(
                f"COPY {table} ({header}) FROM STDIN WITH (FORMAT csv, HEADER true, NULL '')"
            ) as cp:
                cp.write(path.read_bytes())
        conn.execute("SET session_replication_role = DEFAULT")
        bad = {name: conn.execute(sql).fetchone()[0] for name, sql in FK_CHECKS.items()}
        if any(bad.values()):
            conn.rollback()
            print(f"Integrity check failed: {bad}")
            return 1
        for table, _ in TABLES:
            n = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            print(f"{table:<22} {n:>5} rows")
    from set_password import set_demo_passwords  # noqa: E402  (scripts/ is on sys.path)
    print(f"Seed data loaded. Demo sign-in ready for {set_demo_passwords()} accounts (password: DEMO_PASSWORD in .env).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
