"""Week 0 setup checker. Run from the project root:  python scripts/check_setup.py"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

results: list[tuple[bool, str, str]] = []


def check(ok: bool, name: str, hint: str = "") -> bool:
    results.append((ok, name, hint))
    return ok


def main() -> int:
    # 1. Python version
    check(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "Install Python 3.11 or newer")

    # 2. Packages
    missing = []
    for mod in ("dotenv", "openai", "psycopg", "pgvector"):
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    check(not missing, "Required packages", f"Missing {missing} — run: pip install -r requirements.txt")

    # 3. .env
    env_file = ROOT / ".env"
    if not check(env_file.exists(), ".env file", "Run: cp .env.example .env  then fill in values"):
        return report()

    from dotenv import load_dotenv
    load_dotenv(env_file)
    needed = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_CHAT_MODEL", "POSTGRES_PASSWORD"]
    empty = [k for k in needed if not os.getenv(k) or "<" in os.getenv(k, "")]
    check(not empty, ".env values filled", f"Fill in: {empty}")

    # 4. Postgres + pgvector
    try:
        import psycopg
        from copilot.config import postgres_dsn

        with psycopg.connect(postgres_dsn(), connect_timeout=5) as conn:
            ext = conn.execute("SELECT extname FROM pg_extension WHERE extname = 'vector'").fetchone()
        check(ext is not None, "Postgres + pgvector", "Extension missing — recreate DB: docker compose down -v && docker compose up -d")
    except Exception as e:  # noqa: BLE001
        check(False, "Postgres + pgvector", f"Can't connect ({type(e).__name__}). Run: docker compose up -d")

    # 5. LLM round-trip (Azure OpenAI v1 API or any OpenAI-compatible provider)
    try:
        import openai
        from copilot.config import llm_client, load_settings

        s = load_settings()
        resp = llm_client(s).chat.completions.create(
            model=s.chat_model,
            messages=[{"role": "user", "content": "ตอบคำเดียวว่า OK"}],
            # Reasoning models (gpt-5 family) spend tokens thinking first; keep headroom
            max_completion_tokens=1000,
        )
        answer = (resp.choices[0].message.content or "").strip()
        check(bool(answer), f"LLM reply: {answer[:40]!r}", "Empty reply — raise max_completion_tokens or check the model name")
    except Exception as e:  # noqa: BLE001
        hint = f"{type(e).__name__}: {str(e)[:150]}"
        if isinstance(e, openai.AuthenticationError):
            hint += " -> wrong API key"
        elif isinstance(e, openai.NotFoundError):
            hint += " -> check LLM_BASE_URL ends with /openai/v1/ and LLM_CHAT_MODEL is your deployment name"
        elif isinstance(e, openai.RateLimitError):
            hint += " -> no quota. On Azure for Students see docs/setup-azure.md step 5 (quota) and the fallback section"
        elif isinstance(e, openai.APIConnectionError):
            hint += " -> can't reach the endpoint; check LLM_BASE_URL and your internet"
        check(False, "LLM connection", hint)

    return report()


def report() -> int:
    for ok, name, hint in results:
        print(f"[{'OK' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n       -> {hint}"))
    failed = sum(not ok for ok, _, _ in results)
    print("\nAll set — ready for week 1." if not failed else f"\n{failed} check(s) failed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
