"""Execution-accuracy eval for the Data agent (calls the LLM: ~15 questions ≈ 1 THB).

    python scripts/eval_text_to_sql.py            # table to stdout
    python scripts/eval_text_to_sql.py --write    # also docs/eval/text_to_sql.md

Each question runs twice as the same user: the agent's SQL vs a reference SQL.
  scalar — the reference value appears in the agent's first row
  set    — the reference's first column (as a set) equals one of the agent's columns
  refuse — the agent must not run any SQL
Row-level security applies to both, so D07 (another team's tickets) must come back 0.
"""
from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot.agents.data import DataAgent  # noqa: E402
from copilot.data.executor import run_as_user  # noqa: E402
from copilot.data.sql_guard import check_sql  # noqa: E402
from copilot.users import get_user  # noqa: E402


def norm(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, float):
        return round(v, 4)
    return v


def judge(case, ans) -> tuple[bool, str]:
    if case["compare"] == "refuse":
        return ans.result is None, "refused" if ans.result is None else f"ran: {ans.sql}"
    if ans.result is None:
        return False, f"no result ({ans.refused_reason or ans.errors})"
    ref = run_as_user(check_sql(case["reference_sql"]).sql, get_user(case["as"]))
    got = ans.result
    if case["compare"] == "scalar":
        want = norm(ref.rows[0][0]) if ref.rows else None
        first = [norm(v) for v in got.rows[0]] if got.rows else []
        if want in first or (want in (0, None) and not got.rows):
            return True, f"= {want}"
        return False, f"want {want}, got {first[:4]}"
    want = {norm(r[0]) for r in ref.rows}
    cols = [{norm(r[i]) for r in got.rows} for i in range(len(got.columns))]
    if any(c == want for c in cols) or (not want and not got.rows):
        return True, f"{len(want)} rows"
    return False, f"want {sorted(want)[:5]}… got {len(got.rows)} rows"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    cases = [json.loads(x) for x in (ROOT / "data/eval/text_to_sql.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    agent = DataAgent()
    lines = ["| id | as | question | pass | detail | retries |", "|---|---|---|---|---|---|"]
    passed, cost = 0, 0.0
    for c in cases:
        ans = agent.answer(c["question"], get_user(c["as"]))
        ok, detail = judge(c, ans)
        passed += ok
        cost += ans.cost_usd
        lines.append(f"| {c['id']} | {c['as']} | {c['question']} | {'✅' if ok else '❌'} | {detail} | {len(ans.errors)} |")
        print(lines[-1], flush=True)
    summary = f"\nExecution accuracy: {passed}/{len(cases)} ({passed / len(cases):.0%}) · LLM cost ${cost:.4f} ≈ {cost * 33:.2f} THB"
    print(summary)
    if args.write:
        dest = ROOT / "docs" / "eval" / "text_to_sql.md"
        dest.write_text("# Data agent — Text-to-SQL execution accuracy\n\n" + "\n".join(lines) + "\n" + summary + "\n", encoding="utf-8")
        print(f"saved {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
