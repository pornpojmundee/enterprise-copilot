-- Nawa Tech mock business data.
-- Two schemas stand in for two separate company systems:
--   hris  = NawaHR   (people, leave, compensation)
--   itsm  = NawaDesk (IT / HR service tickets)
-- Runs on first DB start; scripts/load_seed.py also runs it (idempotent) before loading CSVs.

CREATE SCHEMA IF NOT EXISTS hris;
CREATE SCHEMA IF NOT EXISTS itsm;

-- ---------- hris ----------
CREATE TABLE IF NOT EXISTS hris.departments (
    dept_id           text PRIMARY KEY,
    name_en           text NOT NULL,
    name_th           text NOT NULL,
    head_employee_id  text
);

CREATE TABLE IF NOT EXISTS hris.teams (
    team_id           text PRIMARY KEY,
    dept_id           text NOT NULL REFERENCES hris.departments(dept_id),
    name_en           text NOT NULL,
    name_th           text NOT NULL,
    lead_employee_id  text
);

CREATE TABLE IF NOT EXISTS hris.employees (
    employee_id        text PRIMARY KEY,           -- e.g. NT0123
    first_name_th      text NOT NULL,
    last_name_th       text NOT NULL,
    first_name_en      text NOT NULL,
    last_name_en       text NOT NULL,
    nickname           text,
    email              text NOT NULL UNIQUE,
    dept_id            text NOT NULL REFERENCES hris.departments(dept_id),
    team_id            text REFERENCES hris.teams(team_id),
    position           text NOT NULL,
    level              text NOT NULL,              -- L1 Junior .. L6 Executive
    manager_id         text REFERENCES hris.employees(employee_id),
    app_role           text NOT NULL,              -- employee | team_lead | manager | hr | it_support | admin | executive
    location           text NOT NULL,
    hire_date          date NOT NULL,
    probation_end_date date NOT NULL,
    employment_status  text NOT NULL,              -- active | probation | resigned
    end_date           date
);
CREATE INDEX IF NOT EXISTS employees_team_idx ON hris.employees(team_id);
CREATE INDEX IF NOT EXISTS employees_manager_idx ON hris.employees(manager_id);

-- Sensitive: only HR/executive should ever reach this (security test SEC1).
CREATE TABLE IF NOT EXISTS hris.compensation (
    employee_id     text PRIMARY KEY REFERENCES hris.employees(employee_id),
    base_salary_thb numeric(12, 2) NOT NULL,
    effective_date  date NOT NULL
);

CREATE TABLE IF NOT EXISTS hris.leave_types (
    code         text PRIMARY KEY,                 -- VAC | SICK | PER
    name_th      text NOT NULL,
    name_en      text NOT NULL,
    paid         boolean NOT NULL,
    allow_half_day boolean NOT NULL
);

CREATE TABLE IF NOT EXISTS hris.leave_balances (
    employee_id   text NOT NULL REFERENCES hris.employees(employee_id),
    year          int  NOT NULL,
    leave_type    text NOT NULL REFERENCES hris.leave_types(code),
    entitled      numeric(4, 1) NOT NULL,
    carried_over  numeric(4, 1) NOT NULL DEFAULT 0,
    used          numeric(4, 1) NOT NULL DEFAULT 0,   -- approved requests
    pending       numeric(4, 1) NOT NULL DEFAULT 0,   -- waiting for approval
    PRIMARY KEY (employee_id, year, leave_type)
);

CREATE TABLE IF NOT EXISTS hris.leave_requests (
    request_id    text PRIMARY KEY,                -- LV-2026-00001
    employee_id   text NOT NULL REFERENCES hris.employees(employee_id),
    leave_type    text NOT NULL REFERENCES hris.leave_types(code),
    start_date    date NOT NULL,
    end_date      date NOT NULL,
    half_day      text CHECK (half_day IN ('am', 'pm')),
    working_days  numeric(4, 1) NOT NULL,
    status        text NOT NULL,                   -- pending | approved | rejected | cancelled
    reason        text,
    approver_id   text REFERENCES hris.employees(employee_id),
    created_at    timestamptz NOT NULL,
    CHECK (end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS leave_requests_emp_idx ON hris.leave_requests(employee_id, start_date);

CREATE TABLE IF NOT EXISTS hris.holidays (
    holiday_date   date PRIMARY KEY,
    name_th        text NOT NULL,
    name_en        text NOT NULL,
    is_substitute  boolean NOT NULL DEFAULT false
);

-- ---------- itsm ----------
CREATE TABLE IF NOT EXISTS itsm.sla_policies (
    priority        text PRIMARY KEY,              -- P1..P4
    description     text NOT NULL,
    response_hours  numeric(5, 2) NOT NULL,
    resolve_hours   numeric(6, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS itsm.tickets (
    ticket_id          text PRIMARY KEY,           -- IT-1042 / HR-0213
    category           text NOT NULL,              -- it | hr
    subcategory        text NOT NULL,
    title              text NOT NULL,
    description        text NOT NULL,
    requester_id       text NOT NULL REFERENCES hris.employees(employee_id),
    requester_team_id  text REFERENCES hris.teams(team_id),
    assigned_team_id   text REFERENCES hris.teams(team_id),
    assignee_id        text REFERENCES hris.employees(employee_id),
    priority           text NOT NULL REFERENCES itsm.sla_policies(priority),
    status             text NOT NULL,              -- open | in_progress | waiting | resolved | closed
    created_at         timestamptz NOT NULL,
    first_response_at  timestamptz,
    resolved_at        timestamptz,
    sla_due_at         timestamptz NOT NULL,
    resolution         text
);
CREATE INDEX IF NOT EXISTS tickets_requester_team_idx ON itsm.tickets(requester_team_id, status);
CREATE INDEX IF NOT EXISTS tickets_assigned_team_idx ON itsm.tickets(assigned_team_id, status);

-- Handy view for "which tickets are past SLA" (UC4).
CREATE OR REPLACE VIEW itsm.v_ticket_sla AS
SELECT t.*,
       CASE
         WHEN t.status IN ('resolved', 'closed') THEN t.resolved_at > t.sla_due_at
         ELSE now() > t.sla_due_at
       END AS sla_breached
FROM itsm.tickets t;
