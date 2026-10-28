-- Knowledge base for the Knowledge agent (week 2).
-- Runs on first DB start; `python -m copilot.kb.index` also runs it (idempotent) before indexing.

CREATE SCHEMA IF NOT EXISTS kb;

CREATE TABLE IF NOT EXISTS kb.documents (
    doc_id          text PRIMARY KEY,          -- HR-001
    title           text NOT NULL,
    category        text NOT NULL,             -- hr | it
    version         text,
    effective_date  date,
    owner           text,
    classification  text NOT NULL DEFAULT 'internal',
    access_roles    text[] NOT NULL,           -- {all} or e.g. {hr,executive}
    source_path     text NOT NULL,
    content_sha256  text NOT NULL,
    indexed_at      timestamptz NOT NULL DEFAULT now()
);

-- One row per section of a document. access_roles is copied from the document so the
-- permission filter runs inside the same query as the search (no post-filtering leaks).
CREATE TABLE IF NOT EXISTS kb.chunks (
    chunk_id      text PRIMARY KEY,            -- HR-001#3.1
    doc_id        text NOT NULL REFERENCES kb.documents(doc_id) ON DELETE CASCADE,
    position      int  NOT NULL,
    section       text NOT NULL,               -- "3.1" or heading text when unnumbered
    heading_path  text NOT NULL,               -- "3. ประเภทการลาและสิทธิ์ > 3.1 ลาพักร้อน"
    content       text NOT NULL,               -- section text as written
    tokens        text NOT NULL,               -- Thai word-tokenized text for BM25
    access_roles  text[] NOT NULL,
    embedding     vector(1024)                 -- bge-m3 (normalized)
);
CREATE INDEX IF NOT EXISTS chunks_doc_idx ON kb.chunks(doc_id, position);
CREATE INDEX IF NOT EXISTS chunks_roles_idx ON kb.chunks USING gin(access_roles);
CREATE INDEX IF NOT EXISTS chunks_embedding_idx ON kb.chunks USING hnsw (embedding vector_cosine_ops);
