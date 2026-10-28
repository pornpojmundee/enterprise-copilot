-- Week 3: what the Data agent may query, and who may see which rows.
--
-- Defense in depth for LLM-generated SQL:
--   1. Semantic layer  — the LLM only knows / may reference views in schema copilot_data
--                        (no salaries, no internal columns).
--   2. Read-only role  — queries run as copilot_reader: SELECT only, READ ONLY transaction, 5 s timeout.
--   3. Row-level security on the base tables — rows are filtered by the asking user
--      (app.user_id etc. set per transaction), so even a "SELECT * FROM tickets" from a
--      team lead only returns their own team's tickets (security test SEC2).
-- The table owner (the app / loader / HRIS API) is not subject to these policies.
-- Idempotent: also applied by scripts/load_seed.py.

-- ---------- role ----------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'copilot_reader') THEN
        CREATE ROLE copilot_reader NOLOGIN;
    END IF;
END $$;
GRANT copilot_reader TO CURRENT_USER;  -- lets the app user SET ROLE copilot_reader

-- ---------- ticket comments (written by the NawaDesk MCP server) ----------
CREATE TABLE IF NOT EXISTS itsm.ticket_comments (
    comment_id  bigserial PRIMARY KEY,
    ticket_id   text NOT NULL REFERENCES itsm.tickets(ticket_id) ON DELETE CASCADE,
    author_id   text NOT NULL REFERENCES hris.employees(employee_id),
    body        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ticket_comments_ticket_idx ON itsm.ticket_comments(ticket_id);

-- ---------- per-request user context ----------
CREATE SCHEMA IF NOT EXISTS copilot_sec;

CREATE OR REPLACE FUNCTION copilot_sec.uid() RETURNS text LANGUAGE sql STABLE
AS $$ SELECT nullif(current_setting('app.user_id', true), '') $$;

CREATE OR REPLACE FUNCTION copilot_sec.app_role() RETURNS text LANGUAGE sql STABLE
AS $$ SELECT coalesce(nullif(current_setting('app.role', true), ''), 'none') $$;

-- Everyone below the current user in the org chart (direct and indirect reports).
CREATE OR REPLACE FUNCTION copilot_sec.my_reports() RETURNS SETOF text LANGUAGE sql STABLE
AS $$
    WITH RECURSIVE r AS (
        SELECT employee_id FROM hris.employees WHERE manager_id = copilot_sec.uid()
        UNION
        SELECT e.employee_id FROM hris.employees e JOIN r ON e.manager_id = r.employee_id
    )
    SELECT employee_id FROM r
$$;

-- ---------- row-level security ----------
ALTER TABLE hris.leave_balances ENABLE ROW LEVEL SECURITY;
ALTER TABLE hris.leave_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE itsm.tickets        ENABLE ROW LEVEL SECURITY;
ALTER TABLE itsm.ticket_comments ENABLE ROW LEVEL SECURITY;

-- Leave: yourself, people in your reporting line, or HR / executives.
DROP POLICY IF EXISTS reader_leave_balances ON hris.leave_balances;
CREATE POLICY reader_leave_balances ON hris.leave_balances FOR SELECT TO copilot_reader USING (
    employee_id = copilot_sec.uid()
    OR employee_id IN (SELECT copilot_sec.my_reports())
    OR copilot_sec.app_role() IN ('hr', 'executive')
);
DROP POLICY IF EXISTS reader_leave_requests ON hris.leave_requests;
CREATE POLICY reader_leave_requests ON hris.leave_requests FOR SELECT TO copilot_reader USING (
    employee_id = copilot_sec.uid()
    OR employee_id IN (SELECT copilot_sec.my_reports())
    OR copilot_sec.app_role() IN ('hr', 'executive')
);

-- Tickets: your own, your reporting line's (UC4), your support queue, or admins/executives.
DROP POLICY IF EXISTS reader_tickets ON itsm.tickets;
CREATE POLICY reader_tickets ON itsm.tickets FOR SELECT TO copilot_reader USING (
    requester_id = copilot_sec.uid()
    OR requester_id IN (SELECT copilot_sec.my_reports())
    OR (copilot_sec.app_role() = 'it_support' AND category = 'it')
    OR (copilot_sec.app_role() = 'hr' AND category = 'hr')
    OR copilot_sec.app_role() IN ('admin', 'executive')
);
DROP POLICY IF EXISTS reader_ticket_comments ON itsm.ticket_comments;
CREATE POLICY reader_ticket_comments ON itsm.ticket_comments FOR SELECT TO copilot_reader USING (
    ticket_id IN (SELECT ticket_id FROM itsm.tickets)   -- inherits the tickets policy
);

-- ---------- semantic layer: the only objects the LLM may query ----------
CREATE SCHEMA IF NOT EXISTS copilot_data;

CREATE OR REPLACE VIEW copilot_data.employees WITH (security_invoker = true) AS
SELECT employee_id, first_name_th, last_name_th, first_name_en, last_name_en, nickname, email,
       dept_id, team_id, position, level, manager_id, location, hire_date, employment_status
FROM hris.employees;

CREATE OR REPLACE VIEW copilot_data.teams WITH (security_invoker = true) AS
SELECT t.team_id, t.name_en, t.name_th, t.dept_id, t.lead_employee_id FROM hris.teams t;

CREATE OR REPLACE VIEW copilot_data.departments WITH (security_invoker = true) AS
SELECT dept_id, name_en, name_th, head_employee_id FROM hris.departments;

CREATE OR REPLACE VIEW copilot_data.holidays WITH (security_invoker = true) AS
SELECT holiday_date, name_th, name_en, is_substitute FROM hris.holidays;

CREATE OR REPLACE VIEW copilot_data.leave_balances WITH (security_invoker = true) AS
SELECT employee_id, year, leave_type, entitled, carried_over, used, pending,
       entitled + carried_over - used - pending AS remaining
FROM hris.leave_balances;

CREATE OR REPLACE VIEW copilot_data.leave_requests WITH (security_invoker = true) AS
SELECT request_id, employee_id, leave_type, start_date, end_date, half_day, working_days, status, reason, created_at
FROM hris.leave_requests;

CREATE OR REPLACE VIEW copilot_data.tickets WITH (security_invoker = true) AS
SELECT ticket_id, category, subcategory, title, description, requester_id, requester_team_id,
       assigned_team_id, assignee_id, priority, status, created_at, first_response_at, resolved_at,
       sla_due_at, resolution,
       status NOT IN ('resolved', 'closed') AS is_open,
       CASE WHEN status IN ('resolved', 'closed') THEN resolved_at > sla_due_at ELSE now() > sla_due_at END AS sla_breached
FROM itsm.tickets;

CREATE OR REPLACE VIEW copilot_data.ticket_comments WITH (security_invoker = true) AS
SELECT comment_id, ticket_id, author_id, body, created_at FROM itsm.ticket_comments;

CREATE OR REPLACE VIEW copilot_data.sla_policies WITH (security_invoker = true) AS
SELECT priority, description, response_hours, resolve_hours FROM itsm.sla_policies;

-- ---------- grants: views + the base tables they read (invoker rights), nothing else ----------
REVOKE ALL ON ALL TABLES IN SCHEMA hris, itsm FROM copilot_reader;
GRANT USAGE ON SCHEMA copilot_data, copilot_sec, hris, itsm TO copilot_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA copilot_data TO copilot_reader;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA copilot_sec TO copilot_reader;
GRANT SELECT ON hris.employees, hris.teams, hris.departments, hris.holidays,
               hris.leave_balances, hris.leave_requests,
               itsm.tickets, itsm.ticket_comments, itsm.sla_policies TO copilot_reader;
-- deliberately NOT granted: hris.compensation, kb.*, anything else
