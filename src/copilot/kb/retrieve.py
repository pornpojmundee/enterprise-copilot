"""Hybrid retrieval over the knowledge base, with permission filtering.

Two searches, fused with Reciprocal Rank Fusion (RRF):
  * vector  — pgvector cosine similarity on bge-m3 embeddings (meaning: "หยุดงานไปหาหมอ" ~ "ลาป่วย")
  * BM25    — keyword scores on Thai-tokenized text (exact terms: "TR-01", "P2", "NawaFlow")

Permission filter (security test SEC1): only chunks whose access_roles overlap the user's
roles are ever searched — in SQL for vectors, and by building a separate BM25 index per
role set. A restricted document never reaches the LLM, so no prompt can leak it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Literal

import psycopg
from psycopg.rows import dict_row
from rank_bm25 import BM25Okapi

from copilot.config import postgres_dsn

from . import kb_schema
from .embeddings import get_embedder
from .index import to_vector_literal
from .text import tokenize

Mode = Literal["hybrid", "vector", "bm25"]
RRF_K = 60
SECTION_PREFIX = re.compile(r"^\d+(?:\.\d+)*\.?\s+")


def roles_for(app_role: str) -> list[str]:
    """Document access roles a user may read: everything public plus their own role."""
    return sorted({"all", app_role})


@dataclass
class Hit:
    chunk_id: str
    doc_id: str
    doc_title: str
    section: str
    heading_path: str
    content: str
    score: float = 0.0
    vector_rank: int | None = None
    vector_sim: float | None = None
    bm25_rank: int | None = None
    bm25_score: float | None = None

    @property
    def citation(self) -> str:
        leaf = SECTION_PREFIX.sub("", self.heading_path.split(" > ")[-1])
        if self.section in ("intro", leaf):
            return f"{self.doc_id} {leaf}"
        return f"{self.doc_id} §{self.section} {leaf}"


@dataclass
class SearchResult:
    query: str
    roles: list[str]
    hits: list[Hit] = field(default_factory=list)
    # True when the closest section in the WHOLE knowledge base is one this user may not read
    # (e.g. an employee asking about executive pay). Only a flag leaves the DB — never content.
    restricted_best_match: bool = False

    @property
    def best_similarity(self) -> float:
        return max((h.vector_sim or 0.0 for h in self.hits), default=0.0)

    @property
    def best_bm25(self) -> float:
        return max((h.bm25_score or 0.0 for h in self.hits), default=0.0)

    @property
    def has_evidence(self) -> bool:
        """Relevance gate: skip the LLM (no cost, no hallucination) when nothing is relevant or
        when the question is really about a document the user can't access.
        Thresholds are calibrated with scripts/calibrate_gate.py."""
        if self.restricted_best_match:
            return False
        min_sim = float(os.getenv("RAG_MIN_SIMILARITY", "0.45"))
        min_bm25 = float(os.getenv("RAG_MIN_BM25", "3.0"))
        return self.best_bm25 >= min_bm25 or self.best_similarity >= min_sim


def rrf_fuse(rankings: list[list[str]], k: int = RRF_K) -> dict[str, float]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, cid in enumerate(ranking, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    return scores


class Retriever:
    def __init__(self, dsn: str | None = None):
        self.dsn = dsn or postgres_dsn()
        self._bm25: dict[tuple[str, ...], tuple[BM25Okapi, list[str]]] = {}  # per (schema, roles)

    def _connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def _bm25_for(self, conn, roles: list[str]) -> tuple[BM25Okapi, list[str]] | None:
        key = (kb_schema(), *roles)
        if key not in self._bm25:
            rows = conn.execute(
                f"SELECT chunk_id, tokens FROM {kb_schema()}.chunks WHERE access_roles && %s ORDER BY chunk_id", (roles,)
            ).fetchall()
            if not rows:
                return None
            self._bm25[key] = (BM25Okapi([r["tokens"].split() for r in rows]), [r["chunk_id"] for r in rows])
        return self._bm25[key]

    def search(self, query: str, app_role: str, k: int = 5, mode: Mode = "hybrid", candidates: int = 20) -> SearchResult:
        roles = roles_for(app_role)
        result = SearchResult(query=query, roles=roles)
        vec_rank: list[str] = []
        sims: dict[str, float] = {}
        bm_rank: list[str] = []
        bm_scores: dict[str, float] = {}

        with self._connect() as conn:
            if mode in ("hybrid", "vector"):
                qv = to_vector_literal(get_embedder().embed([query])[0])
                rows = conn.execute(
                    f"SELECT chunk_id, 1 - (embedding <=> %(q)s::vector) AS sim FROM {kb_schema()}.chunks "
                    "WHERE access_roles && %(roles)s ORDER BY embedding <=> %(q)s::vector LIMIT %(n)s",
                    {"q": qv, "roles": roles, "n": candidates},
                ).fetchall()
                vec_rank = [r["chunk_id"] for r in rows]
                sims = {r["chunk_id"]: float(r["sim"]) for r in rows}
                # Closest section overall, ignoring permissions — used only as a yes/no signal.
                best = conn.execute(
                    f"SELECT access_roles && %(roles)s AS allowed, 1 - (embedding <=> %(q)s::vector) AS sim "
                    f"FROM {kb_schema()}.chunks ORDER BY embedding <=> %(q)s::vector LIMIT 1",
                    {"q": qv, "roles": roles},
                ).fetchone()
                margin = float(os.getenv("RAG_RESTRICTED_MARGIN", "0.03"))
                best_allowed = max(sims.values(), default=0.0)
                result.restricted_best_match = bool(
                    best and not best["allowed"] and float(best["sim"]) >= best_allowed + margin
                )

            if mode in ("hybrid", "bm25"):
                built = self._bm25_for(conn, roles)
                q_tokens = list(tokenize(query))
                if built and q_tokens:
                    bm25, ids = built
                    scored = sorted(zip(ids, bm25.get_scores(q_tokens)), key=lambda x: -x[1])
                    scored = [(cid, float(s)) for cid, s in scored if s > 0][:candidates]
                    bm_rank = [cid for cid, _ in scored]
                    bm_scores = dict(scored)

            fused = rrf_fuse([r for r in (vec_rank, bm_rank) if r])
            top = sorted(fused, key=lambda c: -fused[c])[:k]
            if not top:
                return result
            rows = conn.execute(
                f"SELECT c.chunk_id, c.doc_id, d.title, c.section, c.heading_path, c.content FROM {kb_schema()}.chunks c "
                f"JOIN {kb_schema()}.documents d USING (doc_id) WHERE c.chunk_id = ANY(%s) AND c.access_roles && %s",
                (top, roles),
            ).fetchall()
        by_id = {r["chunk_id"]: r for r in rows}
        for cid in top:
            r = by_id.get(cid)
            if r is None:
                continue
            result.hits.append(Hit(
                chunk_id=cid, doc_id=r["doc_id"], doc_title=r["title"], section=r["section"],
                heading_path=r["heading_path"], content=r["content"], score=fused[cid],
                vector_rank=vec_rank.index(cid) + 1 if cid in vec_rank else None, vector_sim=sims.get(cid),
                bm25_rank=bm_rank.index(cid) + 1 if cid in bm_rank else None, bm25_score=bm_scores.get(cid),
            ))
        return result
