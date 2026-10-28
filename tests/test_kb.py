from pathlib import Path

from copilot.kb.documents import chunk_document, load_all
from copilot.kb.retrieve import rrf_fuse, roles_for
from copilot.kb.text import tokenize

DOCS = Path(__file__).resolve().parents[1] / "data" / "documents"


def test_all_documents_parse_and_chunk():
    docs = load_all(DOCS)
    assert {d.doc_id for d in docs} >= {"HR-001", "HR-004", "IT-001"}
    for d in docs:
        chunks = chunk_document(d)
        assert chunks, d.doc_id
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids)), f"duplicate chunk ids in {d.doc_id}"
        assert all(c.access_roles == d.access_roles for c in chunks)


def test_sections_are_numbered_for_citation():
    leave = next(d for d in load_all(DOCS) if d.doc_id == "HR-001")
    by_id = {c.chunk_id: c for c in chunk_document(leave)}
    assert "HR-001#3.2" in by_id and "ลาป่วย" in by_id["HR-001#3.2"].heading_path
    assert "HR-001#4" in by_id and "วันหยุดชดเชย" in by_id["HR-001#4"].content


def test_restricted_document_keeps_its_roles():
    comp = next(d for d in load_all(DOCS) if d.doc_id == "HR-004")
    assert set(comp.access_roles) == {"hr", "executive"}


def test_thai_tokenizer_splits_words():
    toks = tokenize("ลาพักร้อนต้องยื่นล่วงหน้ากี่วัน")
    assert "ลาพักร้อน" in toks and "ล่วงหน้า" in toks
    assert "ที่" not in tokenize("วันที่ที่ลา")  # stopword removed


def test_rrf_rewards_agreement():
    scores = rrf_fuse([["a", "b", "c"], ["b", "a", "d"]])
    assert max(scores, key=scores.get) in ("a", "b")
    assert scores["a"] > scores["c"] and scores["b"] > scores["d"]


def test_roles_for():
    assert roles_for("employee") == ["all", "employee"]
    assert "hr" in roles_for("hr")
