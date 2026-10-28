"""Build the knowledge-base index: documents -> chunks -> embeddings + BM25 tokens -> Postgres.

    python -m copilot.kb.index            # (re)index data/documents
    python -m copilot.kb.index --dry-run  # show chunks without touching the DB

Re-runnable: wipes kb.* and reloads, so the index always matches the files on disk.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import psycopg

from copilot.config import postgres_dsn

from . import kb_schema
from .documents import chunk_document, load_all
from .embeddings import get_embedder
from .text import tokenize

ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = ROOT / "data" / "documents"
SCHEMA_SQL = ROOT / "db" / "init" / "003_knowledge_base.sql"


def schema_sql(schema: str) -> str:
    sql = SCHEMA_SQL.read_text(encoding="utf-8")
    return sql.replace("SCHEMA IF NOT EXISTS kb;", f"SCHEMA IF NOT EXISTS {schema};").replace("kb.", f"{schema}.")


def to_vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def build(docs_dir: Path = DOCS_DIR, dry_run: bool = False) -> dict:
    docs = load_all(docs_dir)
    chunks = [c for d in docs for c in chunk_document(d)]
    titles = {d.doc_id: d.title for d in docs}
    if dry_run:
        for c in chunks:
            print(f"{c.chunk_id:<14} {c.access_roles} {len(c.content):>5} chars  {c.heading_path}")
        return {"documents": len(docs), "chunks": len(chunks)}

    t0 = time.time()
    embedder = get_embedder()
    vectors = embedder.embed([c.embed_text(titles[c.doc_id]) for c in chunks])
    t_embed = time.time() - t0

    with psycopg.connect(postgres_dsn()) as conn:
        sc = kb_schema()
        conn.execute(schema_sql(sc))
        conn.execute(f"TRUNCATE {sc}.chunks, {sc}.documents")
        with conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO {sc}.documents (doc_id, title, category, version, effective_date, owner, classification,"
                " access_roles, source_path, content_sha256) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                [(d.doc_id, d.title, d.category, d.version, d.effective_date, d.owner, d.classification,
                  d.access_roles, Path(d.source_path).relative_to(ROOT).as_posix(), d.sha256) for d in docs],
            )
            cur.executemany(
                f"INSERT INTO {sc}.chunks (chunk_id, doc_id, position, section, heading_path, content, tokens,"
                " access_roles, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::vector)",
                [(c.chunk_id, c.doc_id, c.position, c.section, c.heading_path, c.content,
                  " ".join(tokenize(f"{titles[c.doc_id]} {c.heading_path} {c.content}")),
                  c.access_roles, to_vector_literal(v)) for c, v in zip(chunks, vectors)],
            )
    return {"documents": len(docs), "chunks": len(chunks), "embedder": embedder.name, "schema": sc,
            "embed_seconds": round(t_embed, 1)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = build(dry_run=args.dry_run)
    print("Indexed:" if not args.dry_run else "Dry run:", stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
