"""Routing accuracy of the orchestrator's router (router call only — ~20 small calls ≈ 0.2 THB).

    python scripts/eval_routing.py            # table
    python scripts/eval_routing.py --write    # also docs/eval/routing.md

A case passes when the chosen agent set equals the expected set (or an accepted alternative).
Per-agent precision/recall shows *which* routes the router confuses.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot.orchestrator import AGENTS, router_node  # noqa: E402
from copilot.users import get_user  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    cases = [json.loads(x) for x in (ROOT / "data/eval/routing.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    tp = {a: 0 for a in AGENTS}
    fp = dict(tp)
    fn = dict(tp)
    lines = ["| id | question | expected | got | pass |", "|---|---|---|---|---|"]
    passed, cost = 0, 0.0
    for c in cases:
        out = router_node({"question": c["question"], "user": asdict(get_user(c["as"])), "history": []})
        got = set(out["plan"]["agents"])
        cost += sum(u["cost_usd"] for u in out["usages"])
        want = set(c["expected"])
        ok = got == want or any(got == set(a) for a in c.get("alt", []))
        passed += ok
        for a in AGENTS:
            tp[a] += a in got and a in want
            fp[a] += a in got and a not in want
            fn[a] += a not in got and a in want
        lines.append(f"| {c['id']} | {c['question']} | {', '.join(sorted(want)) or '—'} | {', '.join(sorted(got)) or '—'} | {'✅' if ok else '❌'} |")
        print(lines[-1], flush=True)
    lines += ["", "| agent | precision | recall |", "|---|---|---|"]
    for a in AGENTS:
        p = tp[a] / (tp[a] + fp[a]) if tp[a] + fp[a] else 1.0
        r = tp[a] / (tp[a] + fn[a]) if tp[a] + fn[a] else 1.0
        lines.append(f"| {a} | {p:.2f} | {r:.2f} |")
    summary = f"\nRouting accuracy (exact agent set): {passed}/{len(cases)} ({passed / len(cases):.0%}) · cost ${cost:.4f} ≈ {cost * 33:.2f} THB"
    print("\n".join(lines[-7:]) + summary)
    if args.write:
        (ROOT / "docs/eval/routing.md").write_text("# Orchestrator routing accuracy\n\n" + "\n".join(lines) + "\n" + summary + "\n", encoding="utf-8")
        print("saved docs/eval/routing.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
