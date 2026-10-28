import pytest

from copilot.data.sql_guard import UnsafeSQL, check_sql


@pytest.mark.parametrize("sql", [
    "SELECT count(*) FROM tickets WHERE is_open",
    "select t.ticket_id, e.first_name_en from copilot_data.tickets t join employees e on e.employee_id = t.requester_id",
    "WITH x AS (SELECT * FROM tickets) SELECT count(*) FROM x",
    "SELECT date_trunc('month', created_at), count(*) FROM tickets GROUP BY 1 ORDER BY 1",
    "SELECT extract(year FROM hire_date), age(now(), hire_date) FROM employees",
    "SELECT * FROM leave_balances WHERE leave_type = 'VAC' AND year = 2026;",
])
def test_allows_safe_queries(sql):
    out = check_sql(sql)
    assert "copilot_data." in out.sql
    assert "LIMIT" in out.sql.upper()


@pytest.mark.parametrize("sql, reason", [
    ("DELETE FROM tickets", "only SELECT"),
    ("UPDATE tickets SET status = 'closed'", "only SELECT"),
    ("DROP VIEW tickets", "only SELECT"),
    ("SELECT 1; SELECT 2", "exactly one"),
    ("SELECT * FROM hris.compensation", "not allowed"),
    ("SELECT * FROM itsm.tickets", "not allowed"),
    ("SELECT * FROM pg_catalog.pg_user", "not allowed"),
    ("SELECT * FROM salaries", "unknown view"),
    ("SELECT set_config('app.role', 'admin', true)", "set_config"),
    ("SELECT * FROM tickets WHERE set_config('app.user_id', 'NT0001', true) IS NOT NULL", "set_config"),
    ("SELECT current_setting('app.user_id')", "current_setting"),
    ("SELECT pg_sleep(30)", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT * FROM tickets FOR UPDATE", "LOCK"),
    ("SELECT * INTO new_table FROM tickets", "INTO"),
    ("", "empty"),
])
def test_rejects_unsafe_queries(sql, reason):
    with pytest.raises(UnsafeSQL, match=reason):
        check_sql(sql)


def test_keeps_existing_limit():
    assert check_sql("SELECT * FROM tickets LIMIT 5").sql.upper().endswith("LIMIT 5")
