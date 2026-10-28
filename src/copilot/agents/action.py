"""Action agent: does things in NawaDesk through its MCP server, with a human in the loop.

    python -m copilot.agents.action "notebook เปิดไม่ติดตั้งแต่เช้า ช่วยเปิดเรื่องให้หน่อย" --as NT0197
    python -m copilot.agents.action "สรุปสถานะ IT-1042 ให้หน่อย" --as NT0048
    python -m copilot.agents.action "ปิด ticket IT-1042 ให้หน่อย" --as NT0082        # SEC5: refused

How it works:
  1. Start the NawaDesk MCP server as the asking user (identity fixed at launch, not a tool argument).
  2. Give the model the server's tools (discovered via MCP list_tools).
  3. Read-only tools (annotation readOnlyHint) run immediately; results go back to the model.
  4. A write tool is never executed directly: the agent returns a PendingAction preview and only
     runs it after the user confirms. The confirmed call goes through the same permission checks.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any

from mcp import Client, StdioServerParameters

from copilot.llm import Usage, chat
from copilot.users import User, get_user

SYSTEM = """คุณคือ Nawa Copilot ผู้ช่วยด้าน IT/HR support ที่ใช้เครื่องมือของระบบ NawaDesk ได้
- ใช้เครื่องมือเมื่อจำเป็น: ดู ticket, ดู ticket ของฉัน, เปิด ticket, เพิ่ม comment, เปลี่ยนสถานะ
- เวลาเปิด ticket: เขียน title สั้นชัด, description รวมอาการ สิ่งที่ลองแล้ว และผลกระทบจากคำพูดผู้ใช้, เลือก subcategory/priority ตามคำอธิบายของเครื่องมือ
- ถ้าข้อมูลไม่พอจะทำงาน ให้ถามผู้ใช้กลับ 1 คำถาม แทนการเดา
- ถ้าเครื่องมือตอบว่า permission denied ให้อธิบายผู้ใช้อย่างสุภาพและบอกทางเลือกที่ทำได้
- ตอบภาษาเดียวกับผู้ใช้ กระชับ"""
MAX_ROUNDS = 4


@dataclass
class PendingAction:
    tool: str
    arguments: dict[str, Any]

    def preview(self) -> str:
        args = "\n".join(f"  {k}: {v}" for k, v in self.arguments.items())
        return f"จะเรียก `{self.tool}` ด้วยข้อมูล:\n{args}"


@dataclass
class ActionResult:
    reply: str
    pending: PendingAction | None = None
    tool_log: list[dict] = field(default_factory=list)
    usages: list[Usage] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usages)


def server_params(user: User) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable, args=["-m", "nawadesk_mcp.server"],
        env={**os.environ, "NAWADESK_ACTING_EMPLOYEE_ID": user.employee_id},
    )


def _text(result) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content).strip()


def _openai_tools(tools) -> tuple[list[dict], set[str]]:
    specs, read_only = [], set()
    for t in tools:
        schema = getattr(t, "input_schema", None) or getattr(t, "inputSchema", None) or {"type": "object"}
        specs.append({"type": "function", "function": {"name": t.name, "description": t.description or "",
                                                       "parameters": schema}})
        ann = t.annotations
        if ann is not None and (getattr(ann, "read_only_hint", None) or getattr(ann, "readOnlyHint", None)):
            read_only.add(t.name)
    return specs, read_only


class ActionAgent:
    def __init__(self, user: User, server: Any = None):
        self.user = user
        self._server = server  # tests pass an in-process MCPServer; default spawns the stdio server

    def _client(self) -> Client:
        return Client(self._server if self._server is not None else server_params(self.user))

    async def arun(self, request: str, history: list[dict] | None = None) -> ActionResult:
        out = ActionResult(reply="")
        async with self._client() as client:
            tools, read_only = _openai_tools((await client.list_tools()).tools)
            messages = [{"role": "system", "content": SYSTEM},
                        {"role": "system", "content": f"ผู้ใช้: {self.user.name} ({self.user.employee_id}, role {self.user.app_role})"},
                        *(history or []), {"role": "user", "content": request}]
            for _ in range(MAX_ROUNDS):
                res = chat(messages, purpose="action.plan", tools=tools)
                out.usages.append(res.usage)
                if not res.tool_calls:
                    out.reply = res.text
                    return out
                write = next((c for c in res.tool_calls if c["name"] not in read_only), None)
                if write:  # human in the loop: stop and ask before changing anything
                    out.pending = PendingAction(write["name"], write["arguments"])
                    out.reply = res.text or "ขอยืนยันก่อนดำเนินการครับ"
                    return out
                messages.append({"role": "assistant", "content": res.text or None, "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["name"], "arguments": json.dumps(c["arguments"], ensure_ascii=False)}}
                    for c in res.tool_calls]})
                for c in res.tool_calls:
                    r = await client.call_tool(c["name"], c["arguments"])
                    text = _text(r)
                    out.tool_log.append({"tool": c["name"], "arguments": c["arguments"], "error": r.is_error, "result": text[:2000]})
                    messages.append({"role": "tool", "tool_call_id": c["id"], "content": text[:6000]})
            out.reply = "ขออภัย ทำรายการนี้ไม่สำเร็จ ลองอธิบายใหม่อีกครั้งครับ"
            return out

    async def aconfirm(self, pending: PendingAction) -> tuple[bool, str]:
        """Execute a previously previewed write. Permission checks still apply server-side."""
        async with self._client() as client:
            r = await client.call_tool(pending.tool, pending.arguments)
            return (not r.is_error), _text(r)

    def run(self, request: str, history: list[dict] | None = None) -> ActionResult:
        return asyncio.run(self.arun(request, history))

    def confirm(self, pending: PendingAction) -> tuple[bool, str]:
        return asyncio.run(self.aconfirm(pending))


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask the Action agent to do something in NawaDesk.")
    ap.add_argument("request")
    ap.add_argument("--as", dest="employee_id", default="NT0082")
    ap.add_argument("--yes", action="store_true", help="confirm write actions without asking")
    ap.add_argument("--show-tools", action="store_true", help="print the tool calls made")
    args = ap.parse_args()

    user = get_user(args.employee_id)
    agent = ActionAgent(user)
    res = agent.run(args.request)
    if args.show_tools:
        for t in res.tool_log:
            print(f"  tool {t['tool']}({t['arguments']}) -> {'ERROR ' if t['error'] else ''}{t['result'][:200]}")
    print(res.reply)
    if res.pending:
        print("\n" + res.pending.preview())
        ok = args.yes or input("\nยืนยันดำเนินการ? [y/N] ").strip().lower() in ("y", "yes")
        if ok:
            success, text = agent.confirm(res.pending)
            print(("✅ สำเร็จ\n" if success else "❌ ไม่สำเร็จ\n") + text)
        else:
            print("ยกเลิกแล้ว — ไม่มีการเปลี่ยนแปลงข้อมูล")
    print(f"\n{len(res.usages)} LLM call(s) · ${res.cost_usd:.5f} ≈ {res.cost_usd * 33:.3f} บาท")
    return 0


if __name__ == "__main__":
    sys.exit(main())
