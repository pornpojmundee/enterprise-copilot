"""Prepare an empty database for the app: schema, seed data, demo passwords, knowledge-base index.

    python scripts/bootstrap.py          # used by the Docker image on every start

In the cloud the database runs as a sidecar with no persistent disk, so each cold start begins
empty and this rebuilds it (≈1 minute): the public demo resets itself. Idempotent, safe to rerun.
Set SEED_ON_START=0 to skip when the database is already loaded.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import psycopg  # noqa: E402

from copilot.config import postgres_dsn  # noqa: E402


def wait_for_db(timeout_s: int = 90) -> None:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            with psycopg.connect(postgres_dsn(), connect_timeout=3) as c:
                c.execute("SELECT 1")
            return
        except psycopg.OperationalError:
            if time.monotonic() > deadline:
                raise
            print("waiting for database...", flush=True)
            time.sleep(2)


def main() -> int:
    if os.getenv("SEED_ON_START", "1") != "1":
        print("SEED_ON_START=0 — skipping bootstrap")
        return 0
    t0 = time.monotonic()
    wait_for_db()
    with psycopg.connect(postgres_dsn()) as c:          # extensions + KB tables (load_seed does the rest)
        for name in ("001_extensions.sql", "003_knowledge_base.sql"):
            c.execute((ROOT / "db" / "init" / name).read_text(encoding="utf-8"))
    import load_seed
    if load_seed.main() != 0:
        return 1
    from copilot.kb.index import build
    print(f"knowledge base: {build()}", flush=True)
    print(f"bootstrap done in {time.monotonic() - t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
