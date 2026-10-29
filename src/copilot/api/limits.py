"""Cost and abuse guards for a public deployment.

- per-user rate limit (RATE_LIMIT_PER_MIN, default 10 questions/minute), in memory
- daily LLM budget (DAILY_LLM_BUDGET_USD, default 0.50 ≈ 16 THB): once today's LLM cost in the
  audit log reaches it, new questions are refused until midnight (UTC) — a stranger with the demo
  password cannot run up the Azure bill.
"""
from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

from copilot import audit


class RateLimiter:
    def __init__(self, per_minute: int | None = None):
        self.per_minute = per_minute or int(os.getenv("RATE_LIMIT_PER_MIN", "10"))
        self._hits: dict[str, deque] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


class DailyBudget:
    def __init__(self, limit_usd: float | None = None, cache_s: float = 20):
        self.limit = limit_usd if limit_usd is not None else float(os.getenv("DAILY_LLM_BUDGET_USD", "0.5"))
        self.cache_s = cache_s
        self._spent, self._at = 0.0, 0.0

    def spent_today(self) -> float:
        if time.monotonic() - self._at > self.cache_s:
            try:
                self._spent = float(audit.summary_today()["cost_usd"])
            except Exception:  # noqa: BLE001 — if the DB is down, chat fails anyway
                pass
            self._at = time.monotonic()
        return self._spent

    def exhausted(self) -> bool:
        return self.limit > 0 and self.spent_today() >= self.limit
