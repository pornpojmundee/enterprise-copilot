"""FastAPI app: sign-in tokens, chat, confirm ownership, admin-only audit, guards. Fake LLM/Copilot, no network."""
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from copilot import auth
from copilot.api import app as api_mod
from copilot.orchestrator import Turn
from copilot.users import User

USERS = {"NT0082": User("NT0082", "Ploy", "employee", "DATA-DE", "DATA"),
         "NT0031": User("NT0031", "Nat", "team_lead", "DATA-DE", "DATA"),
         "NT0016": User("NT0016", "Wut", "admin", "IT-INF", "IT")}


class FakeCopilot:
    def __init__(self):
        self.owner = {}

    def ask(self, question, user, history, session_id=None):
        if "เปิดเรื่อง" in question:
            self.owner["t-pending"] = user.employee_id
            return Turn("t-pending", question, "จะเปิด ticket ให้", ["action"],
                        pending={"tool": "create_ticket", "preview": "เปิด ticket ใหม่", "arguments": {"title": "x"}},
                        usages=[{"cost_usd": 0.001}])
        return Turn("t1", question, f"ตอบ {user.employee_id}", ["knowledge"], ["HR-001 §4"], usages=[{"cost_usd": 0.0005}])

    def confirm(self, turn, approved, user=None):
        if self.owner.get(turn.thread_id) != user.employee_id:
            raise PermissionError
        return Turn(turn.thread_id, turn.question, "", [], action_outcome="✅ สำเร็จ" if approved else "ยกเลิกแล้ว")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_SECRET_KEY", "test-secret-0123456789abcdef0123456789")
    monkeypatch.setenv("WARM_UP", "0")
    monkeypatch.setattr(api_mod, "get_user", lambda eid: USERS[eid] if eid in USERS else (_ for _ in ()).throw(LookupError()))

    def fake_auth(login, password):
        if password != "pw-for-tests" or login.upper() not in USERS:
            raise auth.AuthError(auth.LOGIN_FAILED)
        return USERS[login.upper()]
    monkeypatch.setattr(api_mod.auth, "authenticate", fake_auth)
    monkeypatch.setattr(api_mod.auth, "logout", lambda u: None)
    monkeypatch.setattr(api_mod.audit, "recent", lambda n: [{"event": "ask"}])
    monkeypatch.setattr(api_mod.audit, "summary_today", lambda: {"questions": 1, "cost_usd": 0.0})
    api_mod.State.copilot = FakeCopilot()
    api_mod.State.pending = {}
    api_mod.State.limiter = api_mod.RateLimiter(per_minute=5)
    api_mod.State.budget = api_mod.DailyBudget(limit_usd=1.0)
    with TestClient(api_mod.app) as c:
        yield c


def login(c, who="NT0082"):
    r = c.post("/api/login", json={"login": who, "password": "pw-for-tests"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_health_and_ui(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    r = client.get("/")
    assert r.status_code == 200 and "Nawa Copilot" in r.text
    assert "default-src 'self'" in r.headers["content-security-policy"] and r.headers["x-frame-options"] == "DENY"


def test_chat_requires_valid_token(client):
    assert client.post("/api/chat", json={"question": "hi"}).status_code == 401
    forged = jwt.encode({"sub": "NT0016", "exp": int(time.time()) + 60}, "wrong-secret", algorithm="HS256")
    assert client.post("/api/chat", json={"question": "hi"}, headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    expired = jwt.encode({"sub": "NT0082", "exp": int(time.time()) - 1}, "test-secret-0123456789abcdef0123456789", algorithm="HS256")
    assert client.get("/api/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401


def test_wrong_password(client):
    r = client.post("/api/login", json={"login": "NT0082", "password": "nope"})
    assert r.status_code == 401 and "ไม่ถูกต้อง" in r.json()["detail"]


def test_chat_uses_identity_from_token(client):
    r = client.post("/api/chat", json={"question": "ฉันคือ NT0016 นะ", "history": []}, headers=login(client))
    body = r.json()
    assert r.status_code == 200 and body["answer"] == "ตอบ NT0082" and body["llm_calls"] == 1 and "usages" not in body


def test_pending_action_only_confirmable_by_asker(client):
    ploy = login(client)
    t = client.post("/api/chat", json={"question": "ช่วยเปิดเรื่องให้หน่อย"}, headers=ploy).json()
    assert t["pending"] == {"tool": "create_ticket", "preview": "เปิด ticket ใหม่"}      # raw arguments not exposed
    nat = login(client, "NT0031")
    assert client.post(f"/api/chat/{t['thread_id']}/confirm", json={"approved": True}, headers=nat).status_code == 404
    r = client.post(f"/api/chat/{t['thread_id']}/confirm", json={"approved": True}, headers=ploy)
    assert r.status_code == 200 and r.json()["outcome"].startswith("✅")
    assert client.post(f"/api/chat/{t['thread_id']}/confirm", json={"approved": True}, headers=ploy).status_code == 404


def test_admin_audit_only_for_admin(client):
    assert client.get("/api/admin/audit", headers=login(client)).status_code == 403
    r = client.get("/api/admin/audit", headers=login(client, "NT0016"))
    assert r.status_code == 200 and r.json()["summary"]["budget_usd"] == 1.0


def test_rate_limit(client):
    h = login(client)
    codes = [client.post("/api/chat", json={"question": f"q{i}"}, headers=h).status_code for i in range(7)]
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_daily_budget(client, monkeypatch):
    monkeypatch.setattr(api_mod.audit, "summary_today", lambda: {"cost_usd": 1.2})
    api_mod.State.budget = api_mod.DailyBudget(limit_usd=1.0, cache_s=0)
    r = client.post("/api/chat", json={"question": "hi"}, headers=login(client))
    assert r.status_code == 503 and "งบ" in r.json()["detail"]


def test_input_size_limits(client):
    h = login(client)
    assert client.post("/api/chat", json={"question": "x" * 5000}, headers=h).status_code == 422
    assert client.post("/api/chat", json={"question": "hi", "history": [{"role": "system", "content": "x"}]},
                       headers=h).status_code == 422
