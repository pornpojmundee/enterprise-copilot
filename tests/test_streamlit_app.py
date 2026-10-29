"""Smoke test of the Streamlit demo with fake sign-in + fake Copilot (no LLM, no DB)."""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from copilot import audit, auth, orchestrator  # noqa: E402
from copilot.orchestrator import Turn  # noqa: E402
from copilot.users import User  # noqa: E402

APP = "../app/streamlit_app.py"
ACCOUNTS = {"NT0082": User("NT0082", "ทดสอบ", "employee", "DATA-DE", "DATA"),
            "NT0016": User("NT0016", "แอดมิน", "admin", "IT-INF", "IT")}


class FakeCopilot:
    def ask(self, question, user, history):
        if "เปิดเรื่อง" in question:
            return Turn("t1", question, "จะเปิด ticket ให้ครับ", ["knowledge", "action"], ["IT-001 §3"],
                        pending={"tool": "create_ticket", "arguments": {}, "preview": "จะเรียก create_ticket"},
                        usages=[{"cost_usd": 0.001}], trace=["router → ['knowledge', 'action']"])
        if "บัตร" in question:
            return Turn("t2", "บัตร [เลขบัตรประชาชน]", "ตอบ", [], pii=["thai_id"], notice="🔒 ระบบซ่อนเลขบัตรประชาชน")
        return Turn("t0", question, f"คำตอบสำหรับ {user.employee_id}", ["knowledge"], ["HR-001 §4 การนับวันลา"],
                    usages=[{"cost_usd": 0.0007}], trace=["router → ['knowledge']"])

    def confirm(self, turn, approved, user=None):
        return Turn(turn.thread_id, turn.question, turn.answer, turn.agents,
                    action_outcome="✅ สำเร็จ\n{\"ticket_id\": \"IT-1051\"}" if approved else "ยกเลิกแล้ว")


def fake_authenticate(login, password):
    if password != "pw-for-tests" or login.upper() not in ACCOUNTS:
        raise auth.AuthError(auth.LOGIN_FAILED)
    return ACCOUNTS[login.upper()]


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(orchestrator, "Copilot", FakeCopilot)
    monkeypatch.setattr(auth, "authenticate", fake_authenticate)
    monkeypatch.setattr(auth, "logout", lambda user: None)
    monkeypatch.setattr(audit, "summary_today", lambda: {"questions": 3, "users": 2, "blocked": 1, "pii_masked": 1,
                                                         "failed_logins": 0, "cost_usd": 0.01})
    monkeypatch.setattr(audit, "recent", lambda n=100: [])


def sign_in(login, password="pw-for-tests"):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input[0].set_value(login)
    at.text_input[1].set_value(password)
    at.button[0].click().run()
    return at


def test_chat_is_behind_login():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception and len(at.chat_input) == 0


def test_wrong_password_shows_generic_error():
    at = sign_in("NT0082", "wrong")
    assert at.session_state.user is None and "ไม่ถูกต้อง" in at.error[0].value


def test_ask_and_confirm_flow():
    at = sign_in("NT0082")
    assert not at.exception
    at.chat_input[0].set_value("ฉันเหลือวันลากี่วัน").run()
    assert any("คำตอบสำหรับ NT0082" in m for m in at.markdown.values)
    at.chat_input[0].set_value("notebook เสีย ช่วยเปิดเรื่องให้หน่อย").run()
    confirm = next(b for b in at.button if "ยืนยัน" in b.label)
    confirm.click().run()
    assert any("IT-1051" in s.value for s in at.success)


def test_masked_question_and_notice_shown():
    at = sign_in("NT0082")
    at.chat_input[0].set_value("บัตร 1103702345679").run()
    assert at.session_state.messages[0]["content"] == "บัตร [เลขบัตรประชาชน]"
    assert any("ซ่อน" in w.value for w in at.warning)


def test_logout_clears_session():
    at = sign_in("NT0082")
    at.chat_input[0].set_value("hello").run()
    next(b for b in at.sidebar.button if b.label == "ออกจากระบบ").click().run()
    assert at.session_state.user is None and at.session_state.messages == []


def test_audit_page_only_for_admin():
    assert len(sign_in("NT0082").sidebar.radio) == 0
    at = sign_in("NT0016")
    at.sidebar.radio[0].set_value("Audit log").run()
    assert not at.exception and any(m.label == "คำถามวันนี้" for m in at.metric)
