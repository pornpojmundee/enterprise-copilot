"""Summary agent (UC5): summarize a ticket and find how similar past cases were solved.

    python -m copilot.agents.summary IT-1042 --as NT0048

Similar cases: resolved tickets in the same subcategory ranked by trigram similarity (pg_trgm)
of title + description — cheap, no extra index, works for Thai text. Everything is read through
row-level security, so an employee only ever sees their own history; IT support sees the IT queue.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field

from copilot.data.executor import run_as_user
from copilot.llm import Usage, chat
from copilot.users import User, get_user
from nawadesk_mcp.service import TicketError, TicketService

SYSTEM = """คุณคือผู้ช่วยทีม IT/HR support ของบริษัท นาวาเทค สรุปเคสจากข้อมูลที่ให้มาเท่านั้น
รูปแบบคำตอบ:
1. สรุปเคส (2-3 บรรทัด: อาการ, ผลกระทบ, สถานะ, เกิน SLA หรือไม่)
2. เคสคล้ายกันในอดีตแก้อย่างไร (อ้างอิงเลข ticket เช่น IT-0987)
3. แนะนำขั้นตอนถัดไป
ห้ามแต่งวิธีแก้ที่ไม่มีในข้อมูล ถ้าไม่มีเคสคล้ายให้บอกตรงๆ ตอบภาษาเดียวกับคำถาม"""


@dataclass
class SummaryAnswer:
    ticket_id: str
    answer: str
    similar: list[dict] = field(default_factory=list)
    usages: list[Usage] = field(default_factory=list)


def similar_cases(ticket: dict, user: User, k: int = 5) -> list[dict]:
    res = run_as_user(
        "SELECT ticket_id, title, resolution, priority, created_at::date AS created, "
        "round(public.similarity(title || ' ' || description || ' ' || resolution, %s)::numeric, 2) AS sim "
        "FROM copilot_data.tickets WHERE ticket_id <> %s AND status IN ('resolved', 'closed') "
        "AND coalesce(resolution, '') <> '' AND subcategory = %s "
        "ORDER BY sim DESC, created_at DESC LIMIT %s",
        user, (f"{ticket['title']} {ticket['description']}", ticket["ticket_id"], ticket["subcategory"], k))
    return [dict(zip(res.columns, r)) for r in res.rows]


def summarize(ticket_id: str, user: User, question: str | None = None) -> SummaryAnswer:
    try:
        ticket = TicketService(user).get_ticket(ticket_id)
    except TicketError:
        return SummaryAnswer(ticket_id, f"ไม่พบ ticket {ticket_id} หรือคุณไม่มีสิทธิ์ดู ticket นี้")
    similar = similar_cases(ticket, user)
    comments = "\n".join(f"- {c['created_at'][:16]} {c['author_id']}: {c['body']}" for c in ticket["comments"]) or "(ไม่มี)"
    sims = "\n".join(f"- {s['ticket_id']} (similarity {s['sim']}, {s['priority']}, {s['created']}): {s['title']} → วิธีแก้: {s['resolution']}"
                     for s in similar) or "(ไม่พบเคสที่แก้แล้วในหมวดเดียวกัน)"
    body = (f"คำถาม: {question or 'สรุปเคสนี้'}\n\nTicket {ticket['ticket_id']} [{ticket['priority']}, {ticket['status']}, "
            f"เกิน SLA: {'ใช่' if ticket['sla_breached'] else 'ไม่'}, ทีม {ticket['assigned_team_id']}]\n"
            f"หัวข้อ: {ticket['title']}\nรายละเอียด: {ticket['description']}\nความคิดเห็น:\n{comments}\n\n"
            f"เคสคล้ายกันที่แก้แล้ว:\n{sims}")
    res = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": body}], purpose="summary.ticket")
    return SummaryAnswer(ticket["ticket_id"], res.text, similar, [res.usage])


def main() -> int:
    ap = argparse.ArgumentParser(description="Summarize a ticket and find similar resolved cases.")
    ap.add_argument("ticket_id")
    ap.add_argument("--as", dest="employee_id", default="NT0048")
    args = ap.parse_args()
    ans = summarize(args.ticket_id, get_user(args.employee_id))
    print(ans.answer)
    if ans.similar:
        print("\nเคสคล้ายกัน: " + ", ".join(f"{s['ticket_id']} ({s['sim']})" for s in ans.similar))
    cost = sum(u.cost_usd for u in ans.usages)
    print(f"\n${cost:.5f} ≈ {cost * 33:.3f} บาท")
    return 0


if __name__ == "__main__":
    sys.exit(main())
