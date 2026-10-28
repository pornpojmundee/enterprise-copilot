"""Calibrate the relevance gate from data instead of guessing (no LLM calls — free).

    python scripts/calibrate_gate.py            # show scores + recommended thresholds
    python scripts/calibrate_gate.py --write    # also save docs/eval/gate.md

Questions that SHOULD be answered: knowledge_retrieval.jsonl (expected section present)
and knowledge_gate.jsonl (should_answer=true). Questions that should NOT reach the LLM:
off-topic ones and questions about documents the asker can't read.
The recommended RAG_MIN_SIMILARITY is the lowest best-match similarity among answerable
questions, minus a small safety margin — so no real question is ever blocked.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from copilot.kb.embeddings import get_embedder  # noqa: E402
from copilot.kb.retrieve import Retriever  # noqa: E402

EVAL = ROOT / "data" / "eval"
SAFETY = 0.03


def load(name: str) -> list[dict]:
    return [json.loads(x) for x in (EVAL / name).read_text(encoding="utf-8").splitlines() if x.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    cases = [{**c, "should_answer": True} for c in load("knowledge_retrieval.jsonl") if c["expected"]]
    cases += load("knowledge_gate.jsonl")
    r = Retriever()
    rows = []
    for c in cases:
        res = r.search(c["question"], c["role"], k=5)
        rows.append({**c, "sim": res.best_similarity, "bm25": res.best_bm25, "restricted": res.restricted_best_match})

    answerable = [x for x in rows if x["should_answer"]]
    blockable = [x for x in rows if not x["should_answer"]]
    min_ok = min(x["sim"] for x in answerable)
    rec_sim = round(max(0.0, min_ok - SAFETY), 2)
    # BM25 threshold: only trust keyword matches stronger than any blockable question produced
    rec_bm25 = round(max((x["bm25"] for x in blockable), default=0) + 0.5, 1)

    def passes(x):
        return (not x["restricted"]) and (x["sim"] >= rec_sim or x["bm25"] >= rec_bm25)

    lines = [f"Embedder: {get_embedder().name}", "",
             "| id | kind | role | should answer | best sim | best BM25 | restricted top match | gate (recommended) |",
             "|---|---|---|---|---|---|---|---|"]
    for x in sorted(rows, key=lambda x: (x["should_answer"], x["sim"])):
        ok = passes(x) == x["should_answer"]
        lines.append(f"| {x['id']} | {x['kind']} | {x['role']} | {'yes' if x['should_answer'] else 'no'} | "
                     f"{x['sim']:.3f} | {x['bm25']:.2f} | {'yes' if x['restricted'] else ''} | "
                     f"{'pass' if passes(x) else 'block'}{'' if ok else ' ❌'} |")
    wrong_block = [x["id"] for x in answerable if not passes(x)]
    wrong_pass = [x["id"] for x in blockable if passes(x)]
    lines += ["", f"Recommended: RAG_MIN_SIMILARITY={rec_sim}  RAG_MIN_BM25={rec_bm25}",
              f"Answerable questions blocked: {wrong_block or 'none'}",
              f"Should-block questions that still reach the LLM: {wrong_pass or 'none'}"]
    out = "\n".join(lines)
    print(out)
    if args.write:
        dest = ROOT / "docs" / "eval" / "gate.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("# Relevance gate calibration\n\n" + out + "\n", encoding="utf-8")
        print(f"\nsaved {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
