"""Chat with Nawa Copilot in the terminal (all agents, routed automatically).

    python -m copilot.chat --as NT0082
    python -m copilot.chat --as NT0031 --once "ทีมฉันมี ticket ค้างกี่ใบ และควรแจ้งใครถ้าเกิน SLA"

In the chat:  /as NT0031  switch user · /trace  show routing details · /new  forget history · /exit
"""
from __future__ import annotations

import argparse
import sys

from copilot.orchestrator import Copilot, Turn
from copilot.users import get_user

USD_THB = 33


def show(turn: Turn, trace: bool) -> None:
    print(f"\n{turn.answer}")
    if turn.sources:
        print("\nแหล่งข้อมูล: " + " · ".join(dict.fromkeys(turn.sources)))
    if trace:
        print("\n[trace] " + " | ".join(turn.trace))
    print(f"[{', '.join(turn.agents) or 'no agent'} · {len(turn.usages)} LLM call(s) · "
          f"${turn.cost_usd:.5f} ≈ {turn.cost_usd * USD_THB:.3f} บาท]")


def handle(copilot: Copilot, turn: Turn, auto_yes: bool, trace: bool) -> Turn:
    show(turn, trace)
    if turn.pending:
        print("\n" + turn.pending["preview"])
        ok = auto_yes or input("ยืนยันดำเนินการ? [y/N] ").strip().lower() in ("y", "yes")
        turn = copilot.confirm(turn, ok)
        print(turn.action_outcome)
    return turn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as", dest="employee_id", default="NT0082")
    ap.add_argument("--once", help="ask one question and exit")
    ap.add_argument("--yes", action="store_true", help="auto-confirm write actions")
    ap.add_argument("--trace", action="store_true")
    args = ap.parse_args()

    copilot = Copilot()
    user = get_user(args.employee_id)
    trace = args.trace
    if args.once:
        handle(copilot, copilot.ask(args.once, user), args.yes, trace)
        return 0

    history: list[dict] = []
    print(f"Nawa Copilot — คุยในนาม {user.name} ({user.employee_id}, {user.app_role}). พิมพ์ /exit เพื่อออก")
    while True:
        try:
            q = input(f"\n{user.employee_id}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not q:
            continue
        if q in ("/exit", "/quit"):
            return 0
        if q == "/trace":
            trace = not trace
            print(f"trace {'on' if trace else 'off'}")
            continue
        if q == "/new":
            history = []
            print("เริ่มบทสนทนาใหม่")
            continue
        if q.startswith("/as "):
            user = get_user(q.split()[1].upper())
            history = []
            print(f"ตอนนี้คุยในนาม {user.name} ({user.employee_id}, {user.app_role})")
            continue
        turn = handle(copilot, copilot.ask(q, user, history), args.yes, trace)
        history += [{"role": "user", "content": q}, {"role": "assistant", "content": turn.answer}]
        history = history[-8:]


if __name__ == "__main__":
    sys.exit(main())
