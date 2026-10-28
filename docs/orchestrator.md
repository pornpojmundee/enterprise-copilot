# Orchestrator (week 4)

`src/copilot/orchestrator.py` — LangGraph `StateGraph` ที่รับคำถามเดียวแล้วเลือก agent เอง

## Flow
1. **router** — LLM 1 ครั้ง (`reasoning_effort=minimal`, ≤800 tokens) ตอบเป็น JSON plan: agent ที่ต้องใช้ + คำถามย่อยที่ตีความเองได้ของแต่ละ agent (แก้ "แล้วของทีมล่ะ" จากประวัติบทสนทนา) + วันที่ / เลข ticket ที่ต้องใช้
   plan ถูกตรวจซ้ำในโค้ด: ตัด agent ที่ไม่รู้จัก, ตัด calendar ถ้าไม่มีวันที่, ตัด summary ถ้าไม่มีเลข ticket
2. **agents รันพร้อมกัน** (LangGraph superstep เดียว) — knowledge, data, calendar, summary, action_plan
3. **compose** — ถ้ามี agent เดียว → ส่งคำตอบต่อเลย (ไม่เสีย LLM เพิ่ม) · หลาย agent → LLM 1 ครั้งรวมคำตอบ คงเลขอ้างอิงและตัวเลขตามต้นฉบับ
4. **confirm_action** — ถ้า action agent ต้องเขียนข้อมูล กราฟหยุดด้วย `interrupt()` ผู้ใช้ตอบ y/n แล้ว resume ด้วย `Command(resume=...)` — node นี้เท่านั้นที่รันใหม่ จึงไม่เรียก LLM ซ้ำ และ server ยังตรวจสิทธิ์อีกรอบ

## การตัดสินใจที่สำคัญ
| เรื่อง | เลือก | เหตุผล |
|---|---|---|
| คำนวณวันลา | โค้ด (`tools/calendar.py`) ใช้ปฏิทินวันหยุดจาก DB | LLM มักผิดเรื่อง "4 ธ.ค. 2026 วันอะไร / 7 ธ.ค. หยุดไหม" — ให้ LLM แค่ดึงวันที่ |
| Summary agent หาเคสคล้าย | `pg_trgm similarity()` บน title+description+resolution ในหมวดเดียวกัน ผ่าน RLS | ไม่ต้องสร้าง index เพิ่ม ใช้กับภาษาไทยได้ และเห็นเฉพาะ ticket ที่มีสิทธิ์ · อัปเกรดเป็น vector ได้ภายหลัง |
| Human in the loop | LangGraph `interrupt()` + checkpointer | เป็นกลไกมาตรฐานของ LangGraph, resume ได้แม้ข้าม process ถ้าใช้ checkpointer แบบถาวร |
| Memory | CLI ส่ง 8 ข้อความล่าสุดเป็น history ให้ router | พอสำหรับคำถามต่อเนื่อง และไม่ต้องเก็บ state ข้ามรอบในกราฟ |

## Use case → agents
| UC | คำถาม | agents |
|---|---|---|
| UC1 | ลาศุกร์ 4 ธ.ค. จันทร์เป็นวันหยุดชดเชย นับกี่วัน เหลือพอไหม | knowledge + data + calendar |
| UC2 | ไปสัมมนาเชียงใหม่ 3 วัน ต้องทำอะไรบ้าง | knowledge |
| UC3 | notebook เปิดไม่ติด แจ้งใคร ช่วยเปิดเรื่องให้ | knowledge + action (รอยืนยัน) |
| UC4 | ทีมฉันมี ticket ค้างกี่ใบ อันไหนเกิน SLA | data |
| UC5 | สรุป IT-1042 และเคสคล้าย | summary |

Eval: `python scripts/eval_routing.py --write` → [eval/routing.md](eval/routing.md) (20 คำถาม, exact agent-set match + precision/recall ต่อ agent)
