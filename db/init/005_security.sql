-- Week 5: sign-in credentials and the audit log.
-- Idempotent: scripts/load_seed.py re-applies it on every reload.
--
-- Neither table is granted to copilot_reader (the Data agent's role), so generated SQL can never
-- read password hashes or other people's questions, even if the SQL guard were bypassed.

CREATE SCHEMA IF NOT EXISTS copilot_sec;

CREATE TABLE IF NOT EXISTS copilot_sec.credentials (
    employee_id         text PRIMARY KEY REFERENCES hris.employees(employee_id) ON DELETE CASCADE,
    password_hash       text NOT NULL,                 -- scrypt$n$r$p$salt$hash (see copilot/auth.py)
    failed_attempts     int  NOT NULL DEFAULT 0,
    locked_until        timestamptz,
    password_changed_at timestamptz NOT NULL DEFAULT now(),
    last_login_at       timestamptz
);

-- One row per sign-in event or copilot turn. Questions are stored *after* PII masking (SEC4).
CREATE TABLE IF NOT EXISTS copilot_sec.audit_log (
    id          bigserial PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),
    event       text NOT NULL CHECK (event IN ('login', 'login_failed', 'logout', 'ask', 'confirm')),
    employee_id text,                 -- who (NULL for a failed login with an unknown name)
    app_role    text,
    thread_id   text,
    question    text,                 -- masked
    agents      text[],
    sources     text[],
    sql_text    text,                 -- SQL the Data agent ran, if any
    tool        text,                 -- write tool proposed / confirmed, if any
    guardrail   text,                 -- injection | too_long | content_filter
    pii_types   text[],               -- what was masked, never the value itself
    outcome     text,                 -- answered | blocked | pending | approved | rejected | failed | ok
    llm_calls   int,
    cost_usd    numeric(12, 6),
    latency_ms  int,
    detail      jsonb
);
CREATE INDEX IF NOT EXISTS audit_log_ts_idx ON copilot_sec.audit_log (ts DESC);
CREATE INDEX IF NOT EXISTS audit_log_user_idx ON copilot_sec.audit_log (employee_id, ts DESC);

-- Append-only: nobody (including the app) can edit or erase history through normal SQL.
CREATE OR REPLACE FUNCTION copilot_sec.audit_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'copilot_sec.audit_log is append-only (% not allowed)', TG_OP;
END $$;

DROP TRIGGER IF EXISTS audit_log_no_update ON copilot_sec.audit_log;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE OR DELETE ON copilot_sec.audit_log
    FOR EACH ROW EXECUTE FUNCTION copilot_sec.audit_append_only();
DROP TRIGGER IF EXISTS audit_log_no_truncate ON copilot_sec.audit_log;
CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON copilot_sec.audit_log
    FOR EACH STATEMENT EXECUTE FUNCTION copilot_sec.audit_append_only();

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'copilot_reader') THEN
        REVOKE ALL ON copilot_sec.credentials, copilot_sec.audit_log FROM copilot_reader;
        REVOKE ALL ON SEQUENCE copilot_sec.audit_log_id_seq FROM copilot_reader;
    END IF;
END $$;
