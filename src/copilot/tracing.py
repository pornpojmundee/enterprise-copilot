"""Optional Langfuse tracing. Off unless LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set.

One Copilot turn = one Langfuse trace (user id, session = conversation thread, tags = agents used),
with one generation per LLM call (prompt, output, tokens, estimated cost, latency) nested under it.
Guardrail blocks and Azure content-filter hits show up as WARNING-level observations.

Privacy: questions are already PII-masked before anything is traced, but prompts also contain
retrieved policy text and SQL results. Set LANGFUSE_CAPTURE_CONTENT=0 to send only metadata
(tokens, cost, latency, which agents) — use that for real employee data or a cloud Langfuse.

When disabled, every helper here is a no-op, so the rest of the code never checks.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Iterator

_client = None
_disabled = False


def enabled() -> bool:
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")) and not _disabled


def capture_content() -> bool:
    return os.getenv("LANGFUSE_CAPTURE_CONTENT", "1") == "1"


def _lf():
    global _client, _disabled
    if _client is None:
        try:
            import atexit

            from langfuse import get_client
            _client = get_client()
            atexit.register(_client.flush)   # scripts exit right after their last call
        except Exception as e:  # noqa: BLE001 — tracing must never break the app
            print(f"[tracing] Langfuse disabled: {e}")
            _disabled = True
    return _client


def _content(x: Any) -> Any:
    return x if capture_content() else None


class _Noop:
    def update(self, **_: Any) -> None:
        pass


@contextmanager
def trace(name: str, *, user_id: str, session_id: str, input: Any = None, metadata: dict | None = None) -> Iterator[Any]:
    """Root span for one copilot turn."""
    if not enabled() or _lf() is None:
        yield _Noop()
        return
    lf = _lf()
    with lf.start_as_current_span(name=name, input=_content(input), metadata=metadata) as span:
        lf.update_current_trace(name=name, user_id=user_id, session_id=session_id)
        yield _SpanHandle(lf, span)


class _SpanHandle:
    def __init__(self, lf, span):
        self.lf, self.span = lf, span

    def update(self, *, output: Any = None, tags: list[str] | None = None, metadata: dict | None = None,
               level: str | None = None) -> None:
        self.span.update(output=_content(output), metadata=metadata, **({"level": level} if level else {}))
        if tags is not None or output is not None:
            self.lf.update_current_trace(tags=tags, output=_content(output))


@contextmanager
def generation(name: str, *, model: str, input: Any) -> Iterator[Any]:
    if not enabled() or _lf() is None:
        yield _Noop()
        return
    with _lf().start_as_current_generation(name=name, model=model, input=_content(input)) as gen:
        yield _GenHandle(gen)


class _GenHandle:
    def __init__(self, gen):
        self.gen = gen

    def update(self, *, output: Any = None, input_tokens: int = 0, output_tokens: int = 0, cost_usd: float = 0.0,
               level: str | None = None, status_message: str | None = None) -> None:
        self.gen.update(output=_content(output), usage_details={"input": input_tokens, "output": output_tokens},
                        cost_details={"total": cost_usd},
                        **({"level": level, "status_message": status_message} if level else {}))


def flush() -> None:
    if enabled() and _client is not None:
        _client.flush()
