# Demo video — 3-minute script

Goal: in 3 minutes a hiring manager sees (1) it answers useful questions with sources, (2) different people see
different data, (3) it refuses what it should, (4) it was measured and deployed properly.

## Before recording
- Use the live app (wake it 3 minutes early) or `uvicorn copilot.api.app:app` locally.
- Browser at 1280×720 or 1920×1080, zoom 110–125%, close other tabs and notifications.
- Run each question once beforehand so you know the answers (LLM output varies a little).
- Windows: **Win + Alt + R** (Xbox Game Bar) records the window; **Clipchamp** (built in) trims and adds captions.
  Record voice separately if the room is noisy. Export 1080p MP4, upload to YouTube as *Unlisted*, link it in the README.

## Script
| Time | Screen | Say (EN — Thai version below) |
|---|---|---|
| 0:00–0:15 | README top / sign-in page | "This is Nawa Copilot, an HR and IT assistant for a fictional 200-person Thai company. It answers from policy documents with citations, uses the company's data within each person's permissions, and can open tickets — after you confirm." |
| 0:15–0:50 | Sign in as **NT0082 Ploy**, click **UC1** | "Ploy asks a question that needs three things at once: the leave policy, her own balance, and a day count with a substitute holiday. The router sends it to three agents in parallel — the day count is done in code, not by the model." Point at the agent chips and sources. |
| 0:50–1:10 | Click **SEC1** (salary) | "She asks about salaries. The compensation document is restricted to HR, so it is filtered out *before* retrieval — the model never sees it." |
| 1:10–1:25 | Click **SEC3** | "A prompt-injection attempt is refused before any model call — zero LLM calls, zero cost." |
| 1:25–1:40 | Click **SEC4** | "If someone types a national ID number, it is masked before the model, the logs or a ticket ever see it." |
| 1:40–2:10 | Sign out → **NT0031 Nat** (team lead) → **UC4**, then **SEC2** | "Nat leads the Data Engineering team. Same kind of question, different data: Postgres row-level security only returns his team. Asking about another team returns nothing." Open *ดูการทำงานเบื้องหลัง* to show the SQL. |
| 2:10–2:30 | Sign in as **NT0197 Ton** → **UC3**, press ✅ | "Actions need confirmation. Ton's notebook is broken — the copilot drafts the ticket, he confirms, and the ticket is created through an MCP server that re-checks permissions." |
| 2:30–2:45 | Sign in as **NT0016 Wut** → Audit log | "Everything is in an append-only audit log — questions are stored already masked." |
| 2:45–3:00 | `docs/evaluation.md` results table, then `docs/deploy.md` diagram | "On held-out tests run three times it scores 100% on routing and SQL and 98% on a red-team set. It runs on Azure Container Apps, scales to zero, and uses a managed identity — no API keys. Code and write-ups are on GitHub." |

## Thai narration (if presenting in Thai)
1. "นี่คือ Nawa Copilot ผู้ช่วยด้าน HR และ IT ของบริษัทสมมติขนาด 200 คน ตอบจากเอกสารนโยบายพร้อมอ้างอิง ดึงข้อมูลตามสิทธิ์ของแต่ละคน และเปิด ticket ให้ได้หลังผู้ใช้ยืนยัน"
2. "คำถามของพลอยต้องใช้ 3 อย่างพร้อมกัน — นโยบายการลา ยอดวันลาของเธอ และการนับวันที่มีวันหยุดชดเชย ระบบส่งให้ 3 agent ทำงานขนานกัน และการนับวันทำด้วยโค้ด ไม่ให้ AI คิดเลขเอง"
3. "ถามเงินเดือน — เอกสารค่าตอบแทนจำกัดเฉพาะ HR จึงถูกกรองออกตั้งแต่ก่อนค้นหา AI ไม่เคยเห็นเอกสารนี้เลย"
4. "คำสั่งแบบ prompt injection ถูกปฏิเสธก่อนเรียก AI — ไม่เสียค่าใช้จ่ายเลย"
5. "เลขบัตรประชาชนถูกซ่อนก่อนถึง AI, log และ ticket"
6. "ณัฐเป็นหัวหน้าทีม คำถามคล้ายกันแต่เห็นข้อมูลต่างกัน เพราะ row-level security ใน Postgres ถามข้อมูลทีมอื่นก็ได้ 0"
7. "การแก้ข้อมูลต้องยืนยันก่อนเสมอ และเซิร์ฟเวอร์ตรวจสิทธิ์ซ้ำอีกชั้น"
8. "ทุกอย่างถูกบันทึกใน audit log ที่แก้ไขหรือลบไม่ได้"
9. "ทดสอบด้วยชุดที่ไม่เคยใช้จูน รัน 3 รอบ ได้ 100% ใน routing และ SQL, 98% ใน red-team และ deploy บน Azure แบบ scale-to-zero ไม่ใช้ API key"
