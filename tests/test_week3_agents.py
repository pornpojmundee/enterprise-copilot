"""Data agent, NawaDesk MCP server and Action agent — with a fake LLM (offline, free).
Tickets/comments created here are deleted afterwards so the demo data stays clean."""
import asyncio

import psycopg
import pytest

from copilot.config import postgres_dsn

try:
    with psycopg.connect(postgres_dsn(), connect_timeout=3) as c:
        c.execute("SELECT 1 FROM copilot_data.tickets LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("Postgres with seed data + copilot_data views not available", allow_module_level=True)

from mcp import Client  # noqa: E402

from copilot.agents import action, data  # noqa: E402
from copilot.agents.action import ActionAgent, PendingAction  # noqa: E402
from copilot.agents.data import DataAgent  # noqa: E402
from copilot.llm import ChatResult, Usage  # noqa: E402
from copilot.users import User  # noqa: E402
from nawadesk_mcp.server import build_server  # noqa: E402
from nawadesk_mcp.service import TicketPermissionError, TicketService  # noqa: E402

PLOY = User("NT0082", "Ploy", "employee", "DATA-DE", "DATA")
TON = User("NT0197", "Ton", "employee", "SALES-SMB", "SALES")
NAT = User("NT0031", "Nat", "team_lead", "DATA-DE", "DATA")
FON = User("NT0048", "Fon", "it_support", "IT-SD", "IT")
U = Usage("fake", "test", 10, 5, 0, 0.0, 0.0)


@pytest.fixture
def cleanup():
    with psycopg.connect(postgres_dsn()) as conn:
        before = {r[0] for r in conn.execute("SELECT ticket_id FROM itsm.tickets")}
        comments = conn.execute("SELECT coalesce(max(comment_id), 0) FROM itsm.ticket_comments").fetchone()[0]
    yield
    with psycopg.connect(postgres_dsn()) as conn:
        conn.execute("DELETE FROM itsm.ticket_comments WHERE comment_id > %s", (comments,))
        after = {r[0] for r in conn.execute("SELECT ticket_id FROM itsm.tickets")}
        if after - before:
            conn.execute("DELETE FROM itsm.tickets WHERE ticket_id = ANY(%s)", (list(after - before),))


def scripted(monkeypatch, module, replies):
    """Replace chat() with a script of ChatResults (or callables returning one)."""
    calls = []

    def fake(messages, purpose, max_completion_tokens=None, tools=None):
        calls.append({"messages": messages, "purpose": purpose, "tools": tools})
        r = replies[len(calls) - 1]
        return r(messages) if callable(r) else r
    monkeypatch.setattr(module, "chat", fake)
    return calls


# ---------- Data agent ----------
def test_data_agent_runs_sql_as_user(monkeypatch):
    calls = scripted(monkeypatch, data, [
        ChatResult('{"sql": "SELECT count(*) AS n FROM tickets WHERE is_open", "reason": ""}', U),
        lambda m: ChatResult("ทีมของคุณมี ticket ค้าง " + m[-1]["content"].split("\n")[-1] + " ใบ", U),
    ])
    ans = DataAgent().answer("ทีมฉันมี ticket ค้างกี่ใบ", NAT)
    assert ans.result.rows[0][0] > 0 and "copilot_data.tickets" in ans.sql
    assert len(calls) == 2 and ans.errors == []


def test_data_agent_retries_after_guard_rejection(monkeypatch):
    calls = scripted(monkeypatch, data, [
        ChatResult('{"sql": "SELECT * FROM hris.compensation"}', U),
        ChatResult('{"sql": "SELECT remaining FROM leave_balances WHERE employee_id = \'NT0082\' AND leave_type = \'VAC\'"}', U),
        ChatResult("เหลือ 1.5 วัน", U),
    ])
    ans = DataAgent().answer("ฉันเหลือวันลาพักร้อนกี่วัน", PLOY)
    assert ans.errors and "not allowed" in ans.errors[0]
    assert float(ans.result.rows[0][0]) == 1.5
    assert "previous SQL failed" in calls[1]["messages"][-1]["content"]


def test_data_agent_refusal_costs_one_call(monkeypatch):
    calls = scripted(monkeypatch, data, [ChatResult('{"sql": null, "reason": "salary data is not available"}', U)])
    ans = DataAgent().answer("เงินเดือน CEO เท่าไร", PLOY)
    assert ans.sql is None and ans.refused_reason and len(calls) == 1


# ---------- NawaDesk service ----------
def test_create_comment_and_visibility(cleanup):
    t = TicketService(TON).create_ticket("Notebook เปิดไม่ติด", "จอดำตั้งแต่เช้า", "it", "hardware-notebook", "P2")
    assert t["assigned_team_id"] == "IT-SD" and t["ticket_id"].startswith("IT-")
    TicketService(TON).add_comment(t["ticket_id"], "ลอง hard reset แล้วยังไม่ได้")
    assert len(TicketService(TON).get_ticket(t["ticket_id"])["comments"]) == 1
    assert TicketService(FON).get_ticket(t["ticket_id"])["ticket_id"] == t["ticket_id"]   # IT queue sees it
    with pytest.raises(ValueError, match="not found"):
        TicketService(PLOY).get_ticket(t["ticket_id"])                                   # other employee doesn't


def test_only_support_can_change_status(cleanup):  # SEC5
    with pytest.raises(TicketPermissionError):
        TicketService(PLOY).update_status("IT-1042", "closed", "done")
    t = TicketService(TON).create_ticket("ขอติดตั้ง DBeaver", "ใช้ query ข้อมูล", "it", "software-request", "P4")
    assert TicketService(FON).update_status(t["ticket_id"], "resolved", "ติดตั้งให้แล้ว")["status"] == "resolved"


def test_mcp_server_identity_is_not_a_tool_argument():
    async def go():
        async with Client(build_server("NT0082")) as c:
            tools = (await c.list_tools()).tools
            for t in tools:
                schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None)
                assert not any("employee" in p or "user" in p for p in schema.get("properties", {}))
            r = await c.call_tool("update_ticket_status", {"ticket_id": "IT-1042", "status": "closed", "resolution": "x"})
            assert r.is_error and "permission denied" in r.content[0].text
    asyncio.run(go())


# ---------- Action agent ----------
def test_action_agent_reads_then_answers(monkeypatch):
    scripted(monkeypatch, action, [
        ChatResult("", U, [{"id": "c1", "name": "get_ticket", "arguments": {"ticket_id": "IT-1042"}}]),
        lambda m: ChatResult("IT-1042: notebook เปิดไม่ติด สถานะ waiting" if "IT-1042" in m[-1]["content"] else "?", U),
    ])
    res = ActionAgent(FON, server=build_server("NT0048")).run("สรุป IT-1042")
    assert res.pending is None and "waiting" in res.reply and res.tool_log[0]["tool"] == "get_ticket"


def test_action_agent_asks_before_writing(monkeypatch, cleanup):
    args = {"title": "Notebook เปิดไม่ติด", "description": "จอดำ", "category": "it",
            "subcategory": "hardware-notebook", "priority": "P2"}
    scripted(monkeypatch, action, [ChatResult("จะเปิด ticket ให้นะครับ", U, [{"id": "c1", "name": "create_ticket", "arguments": args}])])
    agent = ActionAgent(TON, server=build_server("NT0197"))
    res = agent.run("notebook เปิดไม่ติด ช่วยเปิดเรื่องให้หน่อย")
    assert res.pending == PendingAction("create_ticket", args) and res.tool_log == []   # nothing written yet
    ok, text = agent.confirm(res.pending)
    assert ok and '"status": "open"' in text
