"""Row-level security and read-only execution (database layer). Needs Postgres + seed data."""
import psycopg
import pytest

from copilot.config import postgres_dsn

try:
    with psycopg.connect(postgres_dsn(), connect_timeout=3) as c:
        c.execute("SELECT 1 FROM copilot_data.tickets LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("Postgres with seed data + copilot_data views not available", allow_module_level=True)

from copilot.data.executor import run_as_user  # noqa: E402
from copilot.users import User  # noqa: E402

PLOY = User("NT0082", "Ploy", "employee", "DATA-DE", "DATA")
NAT = User("NT0031", "Nat", "team_lead", "DATA-DE", "DATA")
FON = User("NT0048", "Fon", "it_support", "IT-SD", "IT")
KWAN = User("NT0061", "Kwan", "hr", "HR-OPS", "HR")
NOBODY = User("NT9999", "nobody", "employee", None, "ENG")


def scalar(sql, user):
    return run_as_user(sql, user).rows[0][0]


def test_employee_sees_only_own_tickets_and_leave():
    assert scalar("SELECT count(*) FROM tickets WHERE requester_id <> 'NT0082'", PLOY) == 0
    assert scalar("SELECT count(*) FROM tickets", PLOY) > 0
    assert scalar("SELECT count(DISTINCT employee_id) FROM leave_balances", PLOY) == 1


def test_team_lead_sees_team_but_not_other_teams():  # SEC2
    assert scalar("SELECT count(*) FROM tickets WHERE requester_team_id = 'DATA-DE'", NAT) > 0
    assert scalar("SELECT count(*) FROM tickets WHERE requester_team_id = 'SALES-SMB'", NAT) == 0
    assert scalar("SELECT count(*) FROM leave_balances b JOIN employees e USING (employee_id) "
                  "WHERE e.team_id <> 'DATA-DE'", NAT) == 0


def test_support_queues():
    assert scalar("SELECT count(*) FROM tickets WHERE category = 'hr'", FON) == 0
    assert scalar("SELECT count(*) FROM tickets WHERE category = 'it'", FON) > 400
    assert scalar("SELECT count(*) FROM tickets WHERE category = 'it' AND requester_id <> 'NT0061'", KWAN) == 0
    assert scalar("SELECT count(DISTINCT employee_id) FROM leave_balances", KWAN) > 150


def test_unknown_user_sees_nothing():
    assert scalar("SELECT count(*) FROM tickets", NOBODY) == 0


def test_salary_table_not_reachable_even_without_guard():  # SEC1 at the DB layer
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_as_user("SELECT * FROM hris.compensation", KWAN)


def test_read_only_even_without_guard():
    with pytest.raises(psycopg.Error):
        run_as_user("DELETE FROM itsm.tickets WHERE ticket_id = 'IT-1042'", FON)
    assert scalar("SELECT count(*) FROM tickets WHERE ticket_id = 'IT-1042'", FON) == 1


def test_statement_timeout(monkeypatch):
    monkeypatch.setenv("DATA_QUERY_TIMEOUT_MS", "200")
    with pytest.raises(psycopg.errors.QueryCanceled):
        run_as_user("SELECT pg_sleep(2)", PLOY)
