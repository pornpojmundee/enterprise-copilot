"""Compare retrieval modes on the golden set (no LLM calls — free to run).

    python scripts/eval_retrieval.py              # prints a table
    python scripts/eval_retrieval.py --write      # also saves docs/eval/retrieval.md

Metrics (for questions with an expected section):
  hit@1 / hit@3 / hit@5 — an expected section is in the top k
  MRR                   — mean of 1/rank of the first expected section
Security (questions with forbidden_docs): leak = a forbidden document appeared at all.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot.kb.embeddings import get_embedder  # noqa: E402
from copilot.kb.retrieve import Retriever  # noqa: E402

GOLDEN = ROOT / "data" / "eval" / "knowledge_retrieval.jsonl"
MODES = ("bm25", "vector", "hybrid")


def evaluate(retriever: Retriever, cases: list[dict], mode: str) -> dict:
    hits = {1: 0, 3: 0, 5: 0}
    rr, n_ranked, leaks, misses = 0.0, 0, 0, []
    for c in cases:
        res = retriever.search(c["question"], c["role"], k=5, mode=mode)
        ids = [h.chunk_id for h in res.hits]
        if any(h.doc_id in c.get("forbidden_docs", []) for h in res.hits):
            leaks += 1
        if not c["expected"]:
            continue
        n_ranked += 1
        rank = next((i for i, cid in enumerate(ids, 1) if cid in c["expected"]), None)
        for k in hits:
            hits[k] += int(rank is not None and rank <= k)
        rr += 1 / rank if rank else 0
        if rank != 1:
            misses.append((c["id"], c["kind"], rank, ids[:3]))
    return {"mode": mode, "n": n_ranked, **{f"hit@{k}": v / n_ranked for k, v in hits.items()},
            "mrr": rr / n_ranked, "leaks": leaks, "misses": misses}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    cases = [json.loads(line) for line in GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    retriever = Retriever()
    rows = [evaluate(retriever, cases, m) for m in MODES]

    lines = [f"Embedder: {get_embedder().name} · golden set: {len(cases)} questions · {date.today()}", "",
             "| mode | hit@1 | hit@3 | hit@5 | MRR | RBAC leaks |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['mode']} | {r['hit@1']:.2f} | {r['hit@3']:.2f} | {r['hit@5']:.2f} | {r['mrr']:.2f} | {r['leaks']} |")
    hybrid = rows[-1]
    if hybrid["misses"]:
        lines += ["", "Hybrid — not ranked #1:"]
        lines += [f"- {i} ({kind}): rank {rank or '>5'} · top3 {top}" for i, kind, rank, top in hybrid["misses"]]
    out = "\n".join(lines)
    print(out)
    if args.write:
        dest = ROOT / "docs" / "eval" / "retrieval.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("# Retrieval evaluation (Knowledge agent)\n\n" + out + "\n", encoding="utf-8")
        print(f"\nsaved {dest.relative_to(ROOT)}")
    if os.getenv("EMBEDDING_BACKEND") == "hash":
        print("\nNOTE: hash embedder is a test stub — vector/hybrid numbers are meaningless here.")
    return 1 if any(r["leaks"] for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
