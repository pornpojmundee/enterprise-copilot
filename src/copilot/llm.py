"""Thin wrapper around the chat model that records tokens and estimated cost for every call.

Every call is appended to logs/llm_usage.jsonl, so `python -m copilot.usage` (or the admin
view in UC6) can answer "how much did the copilot cost this week?".
Prices are per 1M tokens and come from .env — check them against the Azure pricing page.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from .config import llm_client, load_settings

ROOT = Path(__file__).resolve().parents[2]
USAGE_LOG = ROOT / "logs" / "llm_usage.jsonl"


@dataclass
class Usage:
    model: str
    purpose: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int
    cost_usd: float
    latency_s: float

    def summary(self) -> str:
        thb = self.cost_usd * float(os.getenv("USD_THB", "33"))
        return (f"{self.input_tokens} in / {self.output_tokens} out tokens "
                f"(reasoning {self.reasoning_tokens}) · ${self.cost_usd:.5f} ≈ {thb:.3f} บาท · {self.latency_s:.1f}s")


@dataclass
class ChatResult:
    text: str
    usage: Usage
    tool_calls: list[dict] = field(default_factory=list)   # [{"id", "name", "arguments": dict}]


def _price(name: str, default: str) -> float:
    return float(os.getenv(name, default))


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    # Defaults are list prices for gpt-5-mini at time of writing (USD / 1M tokens) — verify on Azure.
    return (input_tokens * _price("LLM_PRICE_INPUT_PER_1M", "0.25")
            + output_tokens * _price("LLM_PRICE_OUTPUT_PER_1M", "2.00")) / 1_000_000


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = llm_client()
    return _client


def chat(messages: list[dict], purpose: str, max_completion_tokens: int | None = None,
         tools: list[dict] | None = None, reasoning_effort: str | None = None) -> ChatResult:
    """One chat completion with a hard output cap (cost guard) and usage logging.
    Pass OpenAI-format `tools` to let the model request tool calls (returned in ChatResult.tool_calls)."""
    settings = load_settings()
    kwargs: dict = {
        "model": settings.chat_model,
        "messages": messages,
        "max_completion_tokens": max_completion_tokens or int(os.getenv("LLM_MAX_COMPLETION_TOKENS", "2000")),
    }
    effort = (reasoning_effort or os.getenv("LLM_REASONING_EFFORT", "low")).strip()
    if effort:  # gpt-5 family: less hidden "thinking" = faster and cheaper
        kwargs["reasoning_effort"] = effort
    if tools:
        kwargs["tools"] = tools
    t0 = time.time()
    resp = _get_client().chat.completions.create(**kwargs)
    latency = time.time() - t0

    u = resp.usage
    reasoning = getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
    usage = Usage(model=settings.chat_model, purpose=purpose, input_tokens=u.prompt_tokens,
                  output_tokens=u.completion_tokens, reasoning_tokens=reasoning,
                  cost_usd=estimate_cost(u.prompt_tokens, u.completion_tokens), latency_s=latency)
    _log(usage)
    msg = resp.choices[0].message
    calls = []
    for tc in msg.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
    return ChatResult(text=(msg.content or "").strip(), usage=usage, tool_calls=calls)


def _log(usage: Usage) -> None:
    try:
        USAGE_LOG.parent.mkdir(exist_ok=True)
        with USAGE_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **asdict(usage)}, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break an answer
