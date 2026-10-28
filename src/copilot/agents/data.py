"""Data agent: answers questions about HR and ticket data with LLM-generated SQL.

    python -m copilot.agents.data "ทีมฉันมี ticket ค้างกี่ใบ อันไหนเกิน SLA" --as NT0031 --show-sql
    python -m copilot.agents.data "ฉันเหลือวันลาพักร้อนกี่วัน" --as NT0082

Flow: question -> LLM writes SQL against the copilot_data views -> SQL guard -> run as the
user (read-only role + row-level security) -> LLM explains the rows in Thai.
One retry: if the guard or Postgres rejects the SQL, the error goes back to the LLM once.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date

import psycopg

from copilot.data.executor import QueryResult, run_as_user
from copilot.data.schema_doc import SCHEMA_DOC
from copilot.data.sql_guard import UnsafeSQL, check_sql
from copilot.llm import Usage, chat
from copilot.users import User, get_user

SQL_SYSTEM = """You translate questions from employees of Nawa Tech into one PostgreSQL SELECT query.

{schema}
Rules:
- Use only the views above. Read-only: never write data.
- "ฉัน/ของฉัน/my" means the asking user (employee_id below). "ทีมฉัน/my team" means the user's team_id
  (for tickets use requester_team_id; for people use employees.team_id). "ลูกทีม" excludes the user.
- "ค้าง/ยังไม่ปิด/open" means is_open = true. "เกิน SLA" means sla_breached = true.
- Current year leave data: year = {year}. Today is {today}.
- Prefer readable output columns (names, titles) and ORDER BY something meaningful.
- If the question cannot be answered from these views (e.g. salaries) or asks to change data,
  return sql = null and explain why in reason.
Reply with JSON only: {{"sql": "...", "reason": "short note"}}"""

ANSWER_SYSTEM = """คุณคือ Nawa Copilot ตอบคำถามพนักงานจากผลลัพธ์ของฐานข้อมูลที่ให้มาเท่านั้น
- ตอบภาษาเดียวกับคำถาม กระชับ ใส่ตัวเลขให้ชัด ใช้ bullet ถ้ามีหลายรายการ (แสดงไม่เกิน 10 รายการ แล้วบอกว่ามีทั้งหมดกี่รายการ)
- ถ้าผลลัพธ์ว่าง ให้บอกว่าไม่พบข้อมูล (อาจเพราะไม่มีข้อมูล หรือคุณไม่มีสิทธิ์เห็นข้อมูลส่วนนั้น)
- ห้ามแต่งข้อมูลที่ไม่มีในผลลัพธ์ ท้ายคำตอบใส่ "(ข้อมูลจาก NawaHR/NawaDesk)" ตามแหล่งที่ใช้"""


@dataclass
class DataAnswer:
    question: str
    answer: str
    sql: str | None = None
    result: QueryResult | None = None
    refused_reason: str | None = None
    errors: list[str] = field(default_factory=list)
    usages: list[Usage] = field(default_factory=list)

    @property
    def cost_usd(self) -> float:
        return sum(u.cost_usd for u in self.usages)


def _user_context(user: User) -> str:
    return (f"Asking user: employee_id={user.employee_id}, name={user.name}, app_role={user.app_role}, "
            f"team_id={user.team_id}, dept_id={user.dept_id}")


def _parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        return json.loads(text[start:end + 1]) if start >= 0 < end else {}


class DataAgent:
    def generate_sql(self, question: str, user: User, feedback: str | None = None) -> tuple[dict, Usage]:
        today = date.today()
        messages = [
            {"role": "system", "content": SQL_SYSTEM.format(schema=SCHEMA_DOC, year=today.year, today=today.isoformat())},
            {"role": "user", "content": f"{_user_context(user)}\nQuestion: {question}"},
        ]
        if feedback:
            messages.append({"role": "user", "content": f"Your previous SQL failed: {feedback}\nReturn corrected JSON."})
        res = chat(messages, purpose="data.sql")
        return _parse_json(res.text), res.usage

    def answer(self, question: str, user: User) -> DataAnswer:
        out = DataAnswer(question=question, answer="")
        feedback = None
        for _attempt in range(2):
            plan, usage = self.generate_sql(question, user, feedback)
            out.usages.append(usage)
            raw_sql = plan.get("sql")
            if not raw_sql:
                out.refused_reason = plan.get("reason") or "cannot be answered from available data"
                out.answer = ("คำถามนี้ตอบจากข้อมูลที่ระบบเข้าถึงได้ไม่ได้ครับ"
                              f" ({out.refused_reason})")
                return out
            try:
                checked = check_sql(raw_sql)
                out.sql = checked.sql
                out.result = run_as_user(checked.sql, user)
                break
            except (UnsafeSQL, psycopg.Error) as e:
                msg = str(e).splitlines()[0]
                out.errors.append(msg)
                feedback = f"{msg}\nSQL was: {raw_sql}"
        if out.result is None:
            out.answer = "ขออภัย ระบบสร้างคำค้นข้อมูลที่ถูกต้องไม่ได้ ลองถามใหม่ให้เจาะจงขึ้นครับ"
            return out

        res = chat([
            {"role": "system", "content": ANSWER_SYSTEM},
            {"role": "user", "content": (f"{_user_context(user)}\nคำถาม: {question}\n\nSQL: {out.sql}\n\n"
                                         f"ผลลัพธ์ ({len(out.result.rows)} แถว):\n{out.result.as_table()}")},
        ], purpose="data.answer")
        out.usages.append(res.usage)
        out.answer = res.text
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask the Data agent about HR / ticket data.")
    ap.add_argument("question")
    ap.add_argument("--as", dest="employee_id", default="NT0082")
    ap.add_argument("--show-sql", action="store_true")
    args = ap.parse_args()
    user = get_user(args.employee_id)
    ans = DataAgent().answer(args.question, user)
    if args.show_sql:
        print(f"--- as {user.employee_id} ({user.app_role}, team {user.team_id}) ---")
        for e in ans.errors:
            print(f"  rejected: {e}")
        print(f"SQL: {ans.sql or '(none)'}")
        if ans.result is not None:
            print(ans.result.as_table(max_rows=10))
        print()
    print(ans.answer)
    calls = len(ans.usages)
    print(f"\n{calls} LLM call(s) · ${ans.cost_usd:.5f} ≈ {ans.cost_usd * 33:.3f} บาท")
    return 0


if __name__ == "__main__":
    sys.exit(main())
