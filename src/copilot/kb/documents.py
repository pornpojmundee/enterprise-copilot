"""Load policy documents and split them into section chunks.

Chunking strategy: split on markdown headings, one chunk per lowest-level section
(### if present, else ##). Policy questions are usually answered by one section, and the
section number ("HR-001 §3.1") doubles as a precise, human-checkable citation.
Each chunk is embedded with its document title + heading path prepended ("contextual
chunk header") so a section like "3.2 ลาป่วย" still carries "นโยบายการลา" in its vector.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SECTION_NO = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+")
MAX_CHARS = 1800


@dataclass
class Document:
    doc_id: str
    title: str
    category: str
    version: str | None
    effective_date: date | None
    owner: str | None
    classification: str
    access_roles: list[str]
    source_path: str
    body: str
    sha256: str


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    position: int
    section: str
    heading_path: str
    content: str
    access_roles: list[str] = field(default_factory=list)

    def embed_text(self, doc_title: str) -> str:
        return f"{doc_title}\n{self.heading_path}\n\n{self.content}"


def load_document(path: Path) -> Document:
    raw = path.read_text(encoding="utf-8")
    m = FRONT_MATTER.match(raw)
    if not m:
        raise ValueError(f"{path.name}: missing YAML front matter")
    meta = yaml.safe_load(m.group(1)) or {}
    for key in ("doc_id", "title", "category", "access_roles"):
        if key not in meta:
            raise ValueError(f"{path.name}: front matter needs '{key}'")
    eff = meta.get("effective_date")
    return Document(
        doc_id=str(meta["doc_id"]),
        title=str(meta["title"]),
        category=str(meta["category"]),
        version=str(meta["version"]) if meta.get("version") is not None else None,
        effective_date=eff if isinstance(eff, date) else (date.fromisoformat(eff) if eff else None),
        owner=meta.get("owner"),
        classification=str(meta.get("classification", "internal")),
        access_roles=[str(r) for r in meta["access_roles"]],
        source_path=path.as_posix(),
        body=raw[m.end():],
        sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


def _section_id(heading: str) -> str:
    m = SECTION_NO.match(heading)
    return m.group(1) if m else heading


def _leaf_section(headings: list[str]) -> str:
    """Section number of the leaf heading; an unnumbered sub-heading inherits its parent's
    number (IT-001 '3. ปัญหาที่พบบ่อย > Notebook เปิดไม่ติด' -> '3'); the heading path keeps the detail."""
    if not headings:
        return "intro"
    for h in reversed(headings):
        m = SECTION_NO.match(h)
        if m:
            return m.group(1)
    return headings[-1]


def chunk_document(doc: Document) -> list[Chunk]:
    """One chunk per leaf section; text before the first ## becomes an 'intro' chunk."""
    sections: list[tuple[list[str], list[str]]] = []  # (heading stack, lines)
    stack: list[tuple[int, str]] = []
    current: list[str] = []

    def flush():
        text = "\n".join(current).strip()
        if text:
            sections.append(([h for _, h in stack], [text]))

    for line in doc.body.splitlines():
        m = HEADING.match(line)
        if m and len(m.group(1)) >= 2:  # '#' is the document title; split on ## and deeper
            flush()
            current = []
            level = len(m.group(1))
            stack = [(lv, h) for lv, h in stack if lv < level] + [(level, m.group(2))]
        elif not (m and len(m.group(1)) == 1):
            current.append(line)
    flush()

    chunks: list[Chunk] = []
    seen: dict[str, int] = {}
    for headings, (text,) in sections:
        section = _leaf_section(headings)
        n = seen.get(section, 0)
        seen[section] = n + 1
        base_id = f"{doc.doc_id}#{section}" + (f"-{n + 1}" if n else "")
        heading_path = " > ".join(headings) if headings else doc.title
        for i, part in enumerate(_split_long(text)):
            chunks.append(Chunk(
                chunk_id=base_id + (f".p{i + 1}" if i else ""),
                doc_id=doc.doc_id,
                position=len(chunks),
                section=section,
                heading_path=heading_path,
                content=part,
                access_roles=list(doc.access_roles),
            ))
    return chunks


def _split_long(text: str) -> list[str]:
    """Split oversized sections on paragraph boundaries, keeping tables/lists intact."""
    if len(text) <= MAX_CHARS:
        return [text]
    parts, buf = [], ""
    for para in re.split(r"\n\s*\n", text):
        if buf and len(buf) + len(para) > MAX_CHARS:
            parts.append(buf.strip())
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts


def load_all(folder: Path) -> list[Document]:
    docs = [load_document(p) for p in sorted(folder.glob("*.md"))]
    ids = [d.doc_id for d in docs]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate doc_id: {dupes}")
    return docs
