"""Sign-in (hashing, lockout, no user enumeration) and the append-only audit log. Needs Postgres."""
import psycopg
import pytest

from copilot.config import postgres_dsn

try:
    with psycopg.connect(postgres_dsn(), connect_timeout=3) as c:
        c.execute("SELECT 1 FROM copilot_sec.audit_log LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("Postgres with week-5 schema not available (run scripts/load_seed.py)", allow_module_level=True)

from copilot import auth  # noqa: E402

EMP = "NT0197"        # Ton — demo account; tests give it a temporary password and restore it after
PW = "correct-horse-42"


@pytest.fixture
def ton():
    auth.set_password(EMP, PW)
    yield
    from set_password import demo_password  # scripts/ is on sys.path via conftest
    auth.set_password(EMP, demo_password())


def _events(n=5):
    with psycopg.connect(postgres_dsn()) as c:
        return c.execute("SELECT event, employee_id, outcome, detail FROM copilot_sec.audit_log "
                         "ORDER BY id DESC LIMIT %s", (n,)).fetchall()


def test_hash_is_salted_and_verifiable():
    a, b = auth.hash_password(PW), auth.hash_password(PW)
    assert a != b and a.startswith("scrypt$") and PW not in a
    assert auth.verify_password(PW, a) and not auth.verify_password("wrong", a)
    assert not auth.verify_password(PW, "garbage")


def test_login_by_id_or_email(ton):
    assert auth.authenticate("nt0197", PW).employee_id == EMP
    with psycopg.connect(postgres_dsn()) as c:
        email = c.execute("SELECT email FROM hris.employees WHERE employee_id = %s", (EMP,)).fetchone()[0]
    assert auth.authenticate(email.upper(), PW).employee_id == EMP
    assert _events(1)[0][:3] == ("login", EMP, "ok")


def test_same_message_for_unknown_user_and_wrong_password(ton):
    with pytest.raises(auth.AuthError) as unknown:
        auth.authenticate("NT9999", PW)
    with pytest.raises(auth.AuthError) as wrong:
        auth.authenticate(EMP, "nope-nope")
    assert str(unknown.value) == str(wrong.value)
    assert _events(1)[0][:3] == ("login_failed", EMP, "failed")


def test_lockout_after_five_failures(ton):
    for _ in range(auth.MAX_FAILED):
        with pytest.raises(auth.AuthError):
            auth.authenticate(EMP, "wrong-password")
    with pytest.raises(auth.AuthError):          # now locked: even the right password fails
        auth.authenticate(EMP, PW)
    assert _events(1)[0][3]["reason"] == "locked"


def test_short_password_rejected():
    with pytest.raises(ValueError):
        auth.set_password(EMP, "short")


def test_audit_log_is_append_only():
    with psycopg.connect(postgres_dsn()) as c:
        for sql in ("UPDATE copilot_sec.audit_log SET question = 'x'",
                    "DELETE FROM copilot_sec.audit_log",
                    "TRUNCATE copilot_sec.audit_log"):
            with pytest.raises(psycopg.errors.RaiseException):
                with c.transaction():
                    c.execute(sql)


def test_data_agent_role_cannot_read_credentials_or_audit():
    with psycopg.connect(postgres_dsn()) as c:
        c.execute("SET ROLE copilot_reader")
        for table in ("copilot_sec.credentials", "copilot_sec.audit_log"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with c.transaction():
                    c.execute(f"SELECT * FROM {table} LIMIT 1")
