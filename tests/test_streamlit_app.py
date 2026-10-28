"""Smoke test of the Streamlit demo with a fake Copilot (no LLM, no DB)."""
import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from copilot import orchestrator, users  # noqa: E402
from copilot.orchestrator import Turn  # noqa: E402
from copilot.users import User  # noqa: E402

APP = "../app/streamlit_app.py"


class FakeCopilot:
    def ask(self, question, user, history):
        if "เปิดเรื่อง" in question:
            return Turn("t1", question, "จะเปิด ticket ให้ครับ", ["knowledge", "action"], ["IT-001 §3"],
                        pending={"tool": "create_ticket", "arguments": {}, "preview": "จะเรียก create_ticket"},
                        usages=[{"cost_usd": 0.001}], trace=["router → ['knowledge', 'action']"])
        return Turn("t0", question, f"คำตอบสำหรับ {user.employee_id}", ["knowledge"], ["HR-001 §4 การนับวันลา"],
                    usages=[{"cost_usd": 0.0007}], trace=["router → ['knowledge']"])

    def confirm(self, turn, approved):
        return Turn(turn.thread_id, turn.question, turn.answer, turn.agents,
                    action_outcome="✅ สำเร็จ\n{\"ticket_id\": \"IT-1051\"}" if approved else "ยกเลิกแล้ว")


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    monkeypatch.setattr(orchestrator, "Copilot", FakeCopilot)
    monkeypatch.setattr(users, "get_user", lambda eid: User(eid, "ทดสอบ", "employee", "DATA-DE", "DATA"))


def test_ask_and_confirm_flow():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    at.chat_input[0].set_value("ฉันเหลือวันลากี่วัน").run()
    assert any("คำตอบสำหรับ NT0082" in m for m in at.markdown.values)
    at.chat_input[0].set_value("notebook เสีย ช่วยเปิดเรื่องให้หน่อย").run()
    confirm = next(b for b in at.button if "ยืนยัน" in b.label)
    confirm.click().run()
    assert any("IT-1051" in s.value for s in at.success)


def test_switch_persona_resets_chat():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.chat_input[0].set_value("hello").run()
    at.sidebar.radio[0].set_value("NT0031").run()
    assert not any(m.get("role") == "user" for m in at.session_state.messages)
