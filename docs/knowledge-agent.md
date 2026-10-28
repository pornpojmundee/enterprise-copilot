# Knowledge agent — design notes

ตอบคำถามนโยบาย HR/IT จากเอกสาร 7 ฉบับใน `data/documents/` พร้อมอ้างอิงหัวข้อ และเคารพสิทธิ์การเข้าถึงเอกสาร

## Pipeline
| ขั้น | ทำอะไร | ทำไมเลือกแบบนี้ |
|---|---|---|
| Chunking | แบ่งตามหัวข้อ markdown (1 chunk = 1 หัวข้อย่อย) เช่น `HR-001#3.2` | คำถามนโยบายส่วนใหญ่ตอบได้ด้วยหัวข้อเดียว และเลขหัวข้อใช้เป็น citation ที่คนตรวจสอบได้ (`HR-001 §3.2`) |
| Contextual header | เติมชื่อเอกสาร + เส้นทางหัวข้อก่อน embed | หัวข้อ "3.2 ลาป่วย" ยังรู้ว่าอยู่ใน "นโยบายการลา" |
| Embeddings | `BAAI/bge-m3` รันบนเครื่อง, 1024 มิติ, normalize | รองรับภาษาไทยดี ฟรี ไม่ส่งเอกสารภายในออกนอกเครื่อง |
| Keyword search | BM25 บนคำที่ตัดด้วย PyThaiNLP (`newmm`) | ภาษาไทยไม่มีช่องว่างระหว่างคำ ถ้าไม่ตัดคำ BM25 ใช้ไม่ได้ · จับคำเฉพาะได้แม่น เช่น `TR-01`, `P2`, `NawaFlow` |
| Fusion | Reciprocal Rank Fusion (k=60) | ไม่ต้องปรับสเกลคะแนนของสองระบบให้เท่ากัน |
| Permission filter | `access_roles && user_roles` ใน SQL + BM25 แยกต่อชุดสิทธิ์ | เอกสารลับ (HR-004) ไม่เคยถูกค้นหรือส่งให้ LLM เลย → prompt ใดๆ ก็ดึงออกมาไม่ได้ (SEC1) |
| Relevance gate | ไม่มีผลที่ผ่าน threshold → ตอบ "ไม่พบ" ทันที · threshold ปรับจากข้อมูลด้วย `scripts/calibrate_gate.py` | ไม่เสียค่า LLM กับคำถามนอกเรื่อง และลด hallucination |
| Restricted short-circuit | ถ้า section ที่ใกล้คำถามที่สุดใน KB ทั้งหมดเป็นเอกสารที่ผู้ถามไม่มีสิทธิ์ → ตอบ "ไม่พบ" โดยไม่เรียก LLM (ส่งออกจาก DB แค่ flag ไม่ใช่เนื้อหา) | คำถามเรื่องเงินเดือนจากพนักงานไม่เสียค่า LLM · ใช้ข้อความเดียวกับ "ไม่พบ" จึงไม่เปิดเผยว่ามีเอกสารนั้นอยู่ · เก็บเป็น audit event ได้ในสัปดาห์ 5 |
| Generation | `gpt-5-mini`, reasoning effort `low`, output cap 2000 tokens | เร็ว ถูก พอสำหรับงานสรุปจากเอกสาร |
| Citations | โมเดลใส่ `[n]` → map กลับเป็นหัวข้อเอกสาร, ตัด `[n]` ที่ชี้ไปที่ไม่มีจริง | ผู้ใช้กดตรวจสอบได้ · ถ้าคำตอบไม่มี citation จะถูก flag `grounded=False` |
| Prompt injection | เอกสารอยู่ใน `<context>` และ system prompt สั่งว่าเป็นข้อมูลเท่านั้น | ด่านแรก — guardrail เต็มรูปแบบมาในสัปดาห์ 5 |
| Cost tracking | ทุกการเรียก LLM บันทึก tokens + ค่าใช้จ่ายประมาณการใน `logs/llm_usage.jsonl` | `python -m copilot.usage` และหน้า admin (UC6) |

## Evaluation
`python scripts/eval_retrieval.py --write` เทียบ BM25 / vector / hybrid บน golden set 20 ข้อ (`data/eval/knowledge_retrieval.jsonl`)
ประกอบด้วยคำถามแบบใช้คำตรง (keyword), ถามอ้อม (paraphrase), use case UC1–UC3 และ security (SEC1/4/5)
ผลล่าสุดอยู่ที่ [docs/eval/retrieval.md](eval/retrieval.md) — ตัวเลขต้องรันด้วย bge-m3 จริงเท่านั้น

Gate calibration: `python scripts/calibrate_gate.py --write` ใช้คำถามที่ควรตอบ (golden set) เทียบกับคำถามที่ไม่ควรถึง LLM (`data/eval/knowledge_gate.jsonl`: นอกเรื่อง + เอกสารลับ) → [docs/eval/gate.md](eval/gate.md)

## ข้อจำกัดที่รู้อยู่ (และแผน)
- Knowledge agent ตอบแค่ส่วน "นโยบาย" — คำถามที่ต้องใช้ข้อมูลส่วนตัว (วันลาคงเหลือ) จะรวมกับ Data agent ในสัปดาห์ 3–4
- ยังไม่มี reranker (cross-encoder) — ถ้า hit@1 ต่ำในคำถามแบบอ้อม จะลองเพิ่ม `bge-reranker-v2-m3`
- index สร้างใหม่ทั้งหมดทุกครั้ง (เอกสารน้อย) — ถ้าเอกสารเยอะขึ้นจะใช้ `content_sha256` ทำ incremental indexing
