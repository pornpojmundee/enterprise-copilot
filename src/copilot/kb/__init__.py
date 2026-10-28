"""Knowledge base: policy documents -> section chunks -> hybrid (vector + BM25) search."""
from __future__ import annotations

import os
import re


def kb_schema() -> str:
    """Postgres schema holding the KB. Tests use KB_SCHEMA=kb_test so they never touch the real index."""
    name = os.getenv("KB_SCHEMA", "kb")
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", name):
        raise ValueError(f"invalid KB_SCHEMA {name!r}")
    return name
