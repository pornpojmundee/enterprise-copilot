"""Orchestrator: one entry point that routes each question to the right agents (LangGraph).

                        ┌─> knowledge ─┐
    question ─> router ─┼─> data ──────┤
                        ├─> calendar ──┼─> compose ─> (pending write?) ─> confirm_action [interrupt] ─> END
                        ├─> summary ───┤
                        └─> action_plan┘
* router: one small LLM call -> JSON plan (which agents + a self-contained sub-question for each).
  Follow-ups ("แล้วของทีมล่ะ") are resolved using the conversation history.
* agents run in parallel (one LangGraph superstep) and write into a shared `results` dict.
* compose: if a single agent answered, its answer is passed through (no extra LLM call);
  otherwise one LLM call merges them, keeping citation markers and numbers exact.
* writes (action agent) pause the graph with LangGraph `interrupt()`; the caller resumes with
  Command(resume=True/False). Only the confirm node re-runs on resume — no repeated LLM calls.
"""
from __future__ import annotations

import json
import operator
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from copilot.llm import Usage, chat
from copilot.users import User

AGENTS = ("knowledge", "data", "calendar", "summary", "action")

ROUTER_SYSTEM = """You route questions from employees of Nawa Tech (Thai software company) to internal agents.
Agents:
- knowledge: company POLICY documents — leave rules, holidays list, travel & expense, IT support process & SLA,
  information security, onboarding, (salary structure: HR/executives only). "How does X work / what are the rules".
- data: FACTS in HR and ticket databases — the user's leave balance/history, team's leave, ticket counts/status/SLA
  breaches, headcount, lists of tickets or people.
- calendar: count how many leave days specific dates cost (weekends/company holidays not counted). Needs dates.
- summary: summarize ONE specific ticket (e.g. IT-1042) and find similar past cases. Needs ticket_id.
- action: DO something in the ticket system — open a ticket, add a comment, change status. Only when the user
  asks for it to be done ("ช่วยเปิดเรื่องให้หน่อย", "ปิด ticket"), never just because a problem is mentioned.
Pick every agent needed (often 2: e.g. policy + the user's own numbers). Write each sub-question so it is
self-contained (resolve "it/that/ของทีมล่ะ" from the history) and in the user's language.
Today is {today}. Dates without a year are in {year} (or next year if already past).
If no agent fits (greeting, chit-chat, outside HR/IT) return agents [] and a short friendly reply in the user's
language saying what you can help with.
Reply with JSON only:
{{"agents": [...], "knowledge_query": str|null, "data_query": str|null, "action_request": str|null,
  "ticket_id": str|null, "dates": {{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}}|null, "reply": str|null}}"""

COMPOSE_SYSTEM = """คุณคือ Nawa Copilot รวมคำตอบจากผู้ช่วยหลายตัวให้เป็นคำตอบเดียวที่ตอบคำถามผู้ใช้ตรงประเด็น
- ใช้เฉพาะข้อมูลจากผลลัพธ์ที่ให้มา ห้ามเพิ่มข้อเท็จจริงใหม่ ตัวเลขต้องตรงตามต้นฉบับ
- คงเครื่องหมายอ้างอิง [1] [2] ของส่วนนโยบายไว้ตามเดิมทุกตัวที่ใช้ และ "(ข้อมูลจาก NawaHR/NawaDesk)" สำหรับส่วนข้อมูล
- ถ้ามีการคำนวณวันลา ให้ใช้ตัวเลขจาก calendar เท่านั้น แล้วเทียบกับยอดคงเหลือว่าพอหรือไม่
- ถ้ามีรายการรอยืนยัน (action) ให้บอกสั้นๆ ว่าจะทำอะไรและรอผู้ใช้ยืนยัน
- กระชับ ใช้ bullet เมื่อมีหลายประเด็น ตอบภาษาเดียวกับคำถาม"""

OUT_OF_SCOPE = "ผมช่วยเรื่องนโยบาย HR/IT, วันลา, ticket และงาน support ภายในบริษัทได้ครับ ลองถามเรื่องเหล่านี้ได้เลย"


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class TurnState(TypedDict, total=False):
    question: str
    user: dict
    history: list[dict]
    plan: dict
    results: Annotated[dict, _merge]
    usages: Annotated[list, operator.add]
    trace: Annotated[list, operator.add]
    answer: str
    pending: dict | None
    action_outcome: str | None


def _user(state: TurnState) -> User:
    return User(**state["user"])


def _parse_json(text: str) -> dict:
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        s, e = text.find("{"), text.rfind("}")
        try:
            return json.loads(text[s:e + 1]) if s >= 0 and e > s else {}
        except json.JSONDecodeError:
            return {}


# ---------- lazily created agents (heavy objects: embedding model, BM25 cache) ----------
_agents: dict[str, Any] = {}


def _knowledge():
    if "knowledge" not in _agents:
        from copilot.agents.knowledge import KnowledgeAgent
        _agents["knowledge"] = KnowledgeAgent()
    return _agents["knowledge"]


def _data():
    if "data" not in _agents:
        from copilot.agents.data import DataAgent
        _agents["data"] = DataAgent()
    return _agents["data"]


# ---------- nodes ----------
def router_node(state: TurnState) -> dict:
    today = date.today()
    history = "\n".join(f"{m['role']}: {m['content'][:400]}" for m in state.get("history", [])[-6:])
    res = chat([
        {"role": "system", "content": ROUTER_SYSTEM.format(today=today.isoformat(), year=today.year)},
        {"role": "user", "content": f"Conversation so far:\n{history or '(none)'}\n\nUser ({state['user']['app_role']}): {state['question']}"},
    ], purpose="router", reasoning_effort="minimal", max_completion_tokens=800)
    plan = _parse_json(res.text)
    agents = [a for a in plan.get("agents", []) if a in AGENTS]
    if "calendar" in agents and not (plan.get("dates") or {}).get("start"):
        agents.remove("calendar")
    if "summary" in agents and not plan.get("ticket_id"):
        agents.remove("summary")
    plan["agents"] = agents
    return {"plan": plan, "usages": [asdict(res.usage)], "trace": [f"router → {agents or 'no agent'}"]}


def route_after_router(state: TurnState) -> list[str]:
    agents = state["plan"]["agents"]
    return [("action_plan" if a == "action" else a) for a in agents] or ["compose"]


def knowledge_node(state: TurnState) -> dict:
    q = state["plan"].get("knowledge_query") or state["question"]
    ans = _knowledge().answer(q, _user(state))
    return {"results": {"knowledge": {
        "text": ans.answer, "citations": [c.label for c in ans.citations], "called_llm": ans.called_llm}},
        "usages": [asdict(ans.usage)] if ans.usage else [],
        "trace": [f"knowledge: {len(ans.citations)} citation(s){'' if ans.called_llm else ', no LLM call'}"]}


def data_node(state: TurnState) -> dict:
    q = state["plan"].get("data_query") or state["question"]
    ans = _data().answer(q, _user(state))
    return {"results": {"data": {"text": ans.answer, "sql": ans.sql,
                                 "rows": len(ans.result.rows) if ans.result else 0}},
            "usages": [asdict(u) for u in ans.usages],
            "trace": [f"data: {'refused' if ans.refused_reason else (str(len(ans.result.rows)) + ' row(s)' if ans.result else 'failed')}"]}


def calendar_node(state: TurnState) -> dict:
    from copilot.tools.calendar import working_days_report
    d = state["plan"]["dates"]
    try:
        rep = working_days_report(date.fromisoformat(d["start"]), date.fromisoformat(d.get("end") or d["start"]))
        return {"results": {"calendar": {"text": rep["text"], "leave_days": rep["leave_days"]}},
                "trace": [f"calendar: {rep['start']}..{rep['end']} = {rep['leave_days']:g} day(s)"]}
    except ValueError as e:
        return {"results": {"calendar": {"text": f"คำนวณวันไม่ได้: {e}"}}, "trace": [f"calendar: error {e}"]}


def summary_node(state: TurnState) -> dict:
    from copilot.agents.summary import summarize
    ans = summarize(state["plan"]["ticket_id"], _user(state), state["question"])
    return {"results": {"summary": {"text": ans.answer, "similar": [s["ticket_id"] for s in ans.similar]}},
            "usages": [asdict(u) for u in ans.usages],
            "trace": [f"summary: {ans.ticket_id}, {len(ans.similar)} similar case(s)"]}


def action_plan_node(state: TurnState) -> dict:
    from copilot.agents.action import ActionAgent
    request = state["plan"].get("action_request") or state["question"]
    res = ActionAgent(_user(state)).run(request, history=state.get("history", [])[-4:])
    out = {"results": {"action": {"text": res.reply, "tools": [t["tool"] for t in res.tool_log]}},
           "usages": [asdict(u) for u in res.usages],
           "trace": [f"action: {'pending ' + res.pending.tool if res.pending else 'no write'}"]}
    if res.pending:
        out["pending"] = {"tool": res.pending.tool, "arguments": res.pending.arguments, "preview": res.pending.preview()}
    return out


def compose_node(state: TurnState) -> dict:
    results = state.get("results", {})
    if not results:
        return {"answer": state["plan"].get("reply") or OUT_OF_SCOPE, "trace": ["compose: direct reply"]}
    if len(results) == 1 and not state.get("pending"):
        (name, r), = results.items()
        return {"answer": r["text"], "trace": [f"compose: pass-through ({name})"]}
    parts = []
    for name in ("calendar", "knowledge", "data", "summary", "action"):
        if name in results:
            parts.append(f"### {name}\n{results[name]['text']}")
    if state.get("pending"):
        parts.append(f"### action รอยืนยัน\n{state['pending']['preview']}")
    res = chat([{"role": "system", "content": COMPOSE_SYSTEM},
                {"role": "user", "content": f"คำถาม: {state['question']}\n\n" + "\n\n".join(parts)}],
               purpose="compose")
    return {"answer": res.text, "usages": [asdict(res.usage)], "trace": [f"compose: merged {len(results)} result(s)"]}


def route_after_compose(state: TurnState) -> str:
    return "confirm_action" if state.get("pending") else END


def confirm_action_node(state: TurnState) -> dict:
    """Pause for the user. On resume, interrupt() returns the user's decision (True/False)."""
    pending = state["pending"]
    approved = interrupt({"preview": pending["preview"], "tool": pending["tool"]})
    if not approved:
        return {"action_outcome": "ยกเลิกแล้ว — ไม่มีการเปลี่ยนแปลงข้อมูล", "trace": ["confirm: rejected by user"]}
    from copilot.agents.action import ActionAgent, PendingAction
    ok, text = ActionAgent(_user(state)).confirm(PendingAction(pending["tool"], pending["arguments"]))
    return {"action_outcome": ("✅ สำเร็จ\n" if ok else "❌ ไม่สำเร็จ\n") + text,
            "trace": [f"confirm: {'done' if ok else 'refused by server'}"]}


def build_graph(checkpointer=None):
    g = StateGraph(TurnState)
    g.add_node("router", router_node)
    g.add_node("knowledge", knowledge_node)
    g.add_node("data", data_node)
    g.add_node("calendar", calendar_node)
    g.add_node("summary", summary_node)
    g.add_node("action_plan", action_plan_node)
    g.add_node("compose", compose_node)
    g.add_node("confirm_action", confirm_action_node)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", route_after_router,
                            ["knowledge", "data", "calendar", "summary", "action_plan", "compose"])
    for n in ("knowledge", "data", "calendar", "summary", "action_plan"):
        g.add_edge(n, "compose")
    g.add_conditional_edges("compose", route_after_compose, ["confirm_action", END])
    g.add_edge("confirm_action", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


# ---------- public API ----------
@dataclass
class Turn:
    thread_id: str
    question: str
    answer: str
    agents: list[str]
    sources: list[str] = field(default_factory=list)
    pending: dict | None = None
    action_outcome: str | None = None
    trace: list[str] = field(default_factory=list)
    usages: list[dict] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(u["cost_usd"] for u in self.usages)


class Copilot:
    def __init__(self):
        self.graph = build_graph()

    def _turn(self, thread_id: str, values: dict, question: str, interrupted: bool) -> Turn:
        results = values.get("results", {})
        sources = list(results.get("knowledge", {}).get("citations", []))
        if "data" in results and results["data"].get("sql"):
            sources.append("NawaHR/NawaDesk (SQL)")
        if "calendar" in results:
            sources.append("ปฏิทินวันหยุดบริษัท HR-002")
        sources += [f"ticket {t}" for t in results.get("summary", {}).get("similar", [])]
        return Turn(thread_id, question, values.get("answer", ""), values.get("plan", {}).get("agents", []),
                    sources, values.get("pending") if interrupted else None, values.get("action_outcome"),
                    values.get("trace", []), values.get("usages", []))

    def ask(self, question: str, user: User, history: list[dict] | None = None) -> Turn:
        thread_id = uuid.uuid4().hex
        config = {"configurable": {"thread_id": thread_id}}
        values = self.graph.invoke({"question": question, "user": asdict(user), "history": history or [],
                                    "results": {}, "usages": [], "trace": [], "pending": None}, config)
        interrupted = bool(self.graph.get_state(config).next)
        return self._turn(thread_id, values, question, interrupted)

    def confirm(self, turn: Turn, approved: bool) -> Turn:
        config = {"configurable": {"thread_id": turn.thread_id}}
        values = self.graph.invoke(Command(resume=approved), config)
        return self._turn(turn.thread_id, values, turn.question, False)
