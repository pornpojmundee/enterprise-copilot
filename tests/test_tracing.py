"""Langfuse tracing: no-op without keys; with keys it must never break or slow a turn's result."""
import json

import pytest

from copilot import llm, orchestrator, tracing
from copilot.llm import ChatResult, Usage

U = Usage("fake", "t", 10, 5, 0, 0.001, 0.0)


def test_disabled_without_keys(monkeypatch):
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    assert not tracing.enabled()
    with tracing.trace("x", user_id="u", session_id="s") as span:
        span.update(output="ok")
    with tracing.generation("g", model="m", input=[]) as gen:
        gen.update(output="ok", input_tokens=1)


def test_enabled_with_unreachable_server_still_answers(monkeypatch):
    pytest.importorskip("langfuse")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_HOST", "http://127.0.0.1:9")
    monkeypatch.setattr(orchestrator.audit, "record", lambda *a, **k: None)
    monkeypatch.setattr(llm, "_chat", lambda *a, **k: ChatResult(json.dumps({"agents": [], "reply": "สวัสดีครับ"}), U))
    monkeypatch.setattr(orchestrator, "chat", llm.chat)          # real wrapper, fake model call
    from copilot.users import User
    turn = orchestrator.Copilot().ask("สวัสดี", User("NT0082", "Ploy", "employee", "DATA-DE", "DATA"), session_id="s1")
    assert turn.answer.startswith("สวัสดี") and tracing.enabled()
