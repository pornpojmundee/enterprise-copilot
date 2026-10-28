"""Summarize LLM spend from logs/llm_usage.jsonl.

    python -m copilot.usage
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime

from .llm import USAGE_LOG


def main() -> None:
    if not USAGE_LOG.exists():
        print("No LLM calls logged yet.")
        return
    by_day: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for line in USAGE_LOG.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        day = datetime.fromisoformat(r["ts"]).astimezone().date().isoformat()
        d = by_day[day]
        d["calls"] += 1
        d["input_tokens"] += r["input_tokens"]
        d["output_tokens"] += r["output_tokens"]
        d["cost_usd"] += r["cost_usd"]
    rate = float(os.getenv("USD_THB", "33"))
    total = 0.0
    print(f"{'date':<12}{'calls':>6}{'in tok':>10}{'out tok':>10}{'USD':>10}{'THB':>9}")
    for day in sorted(by_day):
        d = by_day[day]
        total += d["cost_usd"]
        print(f"{day:<12}{int(d['calls']):>6}{int(d['input_tokens']):>10}{int(d['output_tokens']):>10}"
              f"{d['cost_usd']:>10.4f}{d['cost_usd'] * rate:>9.2f}")
    print(f"{'total':<38}{total:>10.4f}{total * rate:>9.2f}")
    print("(estimates from token counts — the Azure bill is the source of truth)")


if __name__ == "__main__":
    main()
