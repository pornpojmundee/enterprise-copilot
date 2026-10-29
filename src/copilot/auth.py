"""Password sign-in for the demo (company SSO would replace this in a real deployment).

- Passwords are stored as scrypt hashes with a random salt (Python stdlib, no extra dependency).
- 5 wrong passwords lock the account for 15 minutes.
- Unknown user, wrong password, locked or resigned all get the same message, so the login form
  does not reveal which employee IDs exist.
- Every attempt is written to the audit log.

The signed-in User is what every agent receives; identity is never taken from the chat text.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import psycopg

from . import audit
from .config import postgres_dsn
from .users import User, get_user

N, R, P, DKLEN = 2 ** 14, 8, 1, 32
MAX_FAILED = 5
LOCK_MINUTES = 15
MIN_LENGTH = 8
LOGIN_FAILED = "รหัสพนักงาน/อีเมล หรือรหัสผ่านไม่ถูกต้อง (หรือบัญชีถูกล็อกชั่วคราวจากการใส่รหัสผิดหลายครั้ง)"

# The demo personas (docs/demo-personas.md). scripts/load_seed.py gives them DEMO_PASSWORD.
DEMO_ACCOUNTS = ("NT0082", "NT0197", "NT0031", "NT0048", "NT0061", "NT0016", "NT0001")


class AuthError(Exception):
    pass


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=N, r=R, p=P, dklen=DKLEN)
    return f"scrypt${N}${R}${P}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        expected = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
                             dklen=len(expected))
        return hmac.compare_digest(got, expected)
    except (ValueError, TypeError):
        return False


_DUMMY_HASH = hash_password("timing-equaliser")


def set_password(employee_id: str, password: str) -> None:
    if len(password) < MIN_LENGTH:
        raise ValueError(f"password must be at least {MIN_LENGTH} characters")
    with psycopg.connect(postgres_dsn()) as conn:
        conn.execute("""
            INSERT INTO copilot_sec.credentials (employee_id, password_hash) VALUES (%s, %s)
            ON CONFLICT (employee_id) DO UPDATE SET password_hash = EXCLUDED.password_hash,
                failed_attempts = 0, locked_until = NULL, password_changed_at = now()""",
                     (employee_id, hash_password(password)))


def authenticate(login: str, password: str) -> User:
    """Return the signed-in User or raise AuthError(LOGIN_FAILED)."""
    login = (login or "").strip()
    now = datetime.now(timezone.utc)
    with psycopg.connect(postgres_dsn()) as conn:
        emp = conn.execute(
            "SELECT employee_id, app_role, employment_status FROM hris.employees "
            "WHERE upper(employee_id) = upper(%s) OR lower(email) = lower(%s)", (login, login)).fetchone()
        cred = None
        if emp:
            cred = conn.execute(
                "SELECT password_hash, failed_attempts, locked_until FROM copilot_sec.credentials "
                "WHERE employee_id = %s FOR UPDATE", (emp[0],)).fetchone()
        if not emp or not cred:
            verify_password(password, _DUMMY_HASH)          # same cost as a real check
            _fail(emp, "unknown user" if not emp else "no credentials")
        employee_id, app_role, status = emp
        pw_hash, failed, locked_until = cred
        if locked_until and locked_until > now:
            _fail(emp, "locked")
        ok = verify_password(password, pw_hash)
        if ok and status != "resigned":
            conn.execute("UPDATE copilot_sec.credentials SET failed_attempts = 0, locked_until = NULL, "
                         "last_login_at = now() WHERE employee_id = %s", (employee_id,))
        elif not ok:
            failed += 1
            lock = now + timedelta(minutes=LOCK_MINUTES) if failed >= MAX_FAILED else None
            conn.execute("UPDATE copilot_sec.credentials SET failed_attempts = %s, locked_until = %s "
                         "WHERE employee_id = %s", (0 if lock else failed, lock, employee_id))
            conn.commit()
            _fail(emp, f"wrong password ({failed}/{MAX_FAILED})" + (" → locked" if lock else ""))
        else:
            _fail(emp, "resigned")
    user = get_user(employee_id)
    audit.record("login", employee_id=user.employee_id, app_role=user.app_role, outcome="ok")
    return user


def _fail(emp, reason: str):
    audit.record("login_failed", employee_id=emp[0] if emp else None, app_role=emp[1] if emp else None,
                 outcome="failed", detail={"reason": reason})
    raise AuthError(LOGIN_FAILED)


def logout(user: User) -> None:
    audit.record("logout", employee_id=user.employee_id, app_role=user.app_role, outcome="ok")
