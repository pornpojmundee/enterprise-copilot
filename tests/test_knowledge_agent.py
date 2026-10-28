"""Knowledge agent tests. Need Postgres with seed data; the KB is indexed with the hash
embedder and the LLM is replaced by a fake, so these run offline and cost nothing."""
import os

import psycopg
import pytest

from copilot.config import postgres_dsn

try:
    with psycopg.connect(postgres_dsn(), connect_timeout=3) as c:
        c.execute("SELECT 1 FROM hris.employees LIMIT 1")
except Exception:  # noqa: BLE001
    pytest.skip("Postgres with seed data not available", allow_module_level=True)

from copilot.agents import knowledge  # noqa: E402
from copilot.agents.knowledge import KnowledgeAgent, map_citations  # noqa: E402
from copilot.kb import embeddings  # noqa: E402
from copilot.kb.index import build  # noqa: E402
from copilot.kb.retrieve import Hit, Retriever  # noqa: E402
from copilot.llm import ChatResult, Usage  # noqa: E402
from copilot.users import User  # noqa: E402

EMPLOYEE = User("NT0082", "พิมพ์ชนก ศรีสวัสดิ์", "employee", "DATA-DE", "DATA")
HR = User("NT0061", "กมลชนก บุญมา", "hr", "HR-OPS", "HR")


@pytest.fixture(scope="module", autouse=True)
def hash_index():
    """Index into a separate schema (kb_test) with the offline embedder — the real kb index is untouched."""
    saved = {k: os.environ.get(k) for k in ("EMBEDDING_BACKEND", "KB_SCHEMA")}
    os.environ.update(EMBEDDING_BACKEND="hash", KB_SCHEMA="kb_test")
    embeddings.get_embedder.cache_clear()
    build()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    embeddings.get_embedder.cache_clear()


@pytest.fixture
def fake_llm(monkeypatch):
    calls = []

    def fake_chat(messages, purpose, max_completion_tokens=None):
        calls.append(messages)
        return ChatResult("ลาป่วยตั้งแต่ 3 วันทำงานขึ้นไปต้องมีใบรับรองแพทย์ [1] ดูเพิ่ม [9]",
                          Usage("fake", purpose, 100, 20, 0, 0.0, 0.0))

    monkeypatch.setattr(knowledge, "chat", fake_chat)
    return calls


def test_restricted_doc_never_retrieved_for_employee():
    r = Retriever()
    for q in ("เงินเดือนระดับ Team Lead เท่าไร", "โบนัสผู้บริหาร", "โครงสร้างค่าตอบแทน CONFIDENTIAL"):
        for mode in ("hybrid", "vector", "bm25"):
            res = r.search(q, "employee", k=10, mode=mode)
            assert all(h.doc_id != "HR-004" for h in res.hits), (q, mode)


def test_restricted_doc_retrieved_for_hr():
    res = Retriever().search("เงินเดือนระดับ Team Lead เท่าไร", "hr", k=5)
    assert any(h.doc_id == "HR-004" for h in res.hits)


def test_answer_maps_citations_and_drops_bad_markers(fake_llm):
    ans = KnowledgeAgent().answer("ลาป่วยกี่วันต้องมีใบรับรองแพทย์", EMPLOYEE)
    assert ans.called_llm and ans.grounded
    assert [c.n for c in ans.citations] == [1]
    assert "[9]" not in ans.answer            # marker pointing at nothing is removed
    prompt = fake_llm[0][1]["content"]
    assert "<context>" in prompt and "HR-004" not in prompt


def test_off_topic_question_skips_llm(fake_llm, monkeypatch):
    monkeypatch.setenv("RAG_MIN_SIMILARITY", "2")  # hash embedder: only BM25 can count as evidence
    ans = KnowledgeAgent().answer("สูตรทำต้มยำกุ้งน้ำข้น", EMPLOYEE)
    assert not ans.called_llm and not fake_llm
    assert "ไม่พบข้อมูล" in ans.answer


def test_map_citations_order():
    hits = [Hit(f"D#{i}", "D", "Doc", str(i), f"{i}. sec", "x") for i in range(1, 4)]
    text, cites = map_citations("a [3] b [1][3] c [7]", hits)
    assert [c.n for c in cites] == [3, 1]
    assert "[7]" not in text
