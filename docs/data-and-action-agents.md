# Data agent + Action agent (week 3)

## Data agent — Text-to-SQL ที่ปลอดภัยแม้ LLM เขียน SQL ผิดหรือถูกหลอก
ความปลอดภัยไม่ได้ฝากไว้กับ prompt — มี 3 ชั้น แต่ละชั้นทำงานได้แม้ชั้นอื่นพลาด:

| ชั้น | อยู่ที่ไหน | กันอะไร |
|---|---|---|
| 1. Semantic layer | views ใน schema `copilot_data` (`db/init/004_copilot_data.sql`) | LLM เห็นแค่ข้อมูลที่ตั้งใจเปิด — ไม่มีเงินเดือน ไม่มีคอลัมน์ภายใน |
| 2. SQL guard | `src/copilot/data/sql_guard.py` (sqlglot) | 1 statement, SELECT เท่านั้น, เฉพาะ views ที่อนุญาต, ห้าม `FOR UPDATE`/`INTO`, **function allowlist** (กัน `set_config()` ที่จะแก้ตัวตนผู้ใช้, `pg_sleep`, `pg_read_file`) และเติม LIMIT |
| 3. Database | role `copilot_reader` + `READ ONLY` transaction + `statement_timeout` 5 s + **row-level security** | แถวถูกกรองตามผู้ถามในตัว Postgres — หัวหน้าทีม Data ถามข้อมูลทีม Sales ได้ 0 แถว (SEC2), ไม่มีสิทธิ์ `hris.compensation` เลย (SEC1), เขียนข้อมูลไม่ได้ |

นโยบาย RLS (ตามผังองค์กร ไม่ใช่ตาม role อย่างเดียว):
- **ticket**: ของตัวเอง · ของลูกทีมทั้งสาย (หัวหน้า/ผู้อำนวยการ) · คิวของตัวเอง (IT Support เห็น IT, HR เห็น HR) · admin/ผู้บริหารเห็นทั้งหมด
- **วันลา**: ของตัวเอง · ของลูกทีมทั้งสาย · HR/ผู้บริหาร
- ไม่มี user context = 0 แถว (ปลอดภัยไว้ก่อน)

ขั้นตอน: LLM สร้าง SQL (JSON) → guard → รันในนามผู้ใช้ → ถ้า guard/Postgres ปฏิเสธ ส่ง error กลับให้ LLM แก้ 1 ครั้ง → LLM สรุปผลเป็นภาษาไทย
คำถามที่ตอบจากข้อมูลไม่ได้ (เงินเดือน, สั่งลบข้อมูล) → LLM ตอบ `sql: null` → ไม่รันอะไรเลย

Eval: `python scripts/eval_text_to_sql.py --write` → [eval/text_to_sql.md](eval/text_to_sql.md) — 15 คำถามจาก 4 personas, วัด execution accuracy เทียบกับ reference SQL ที่รันในนามผู้ใช้คนเดียวกัน

## Action agent — ทำงานใน NawaDesk ผ่าน MCP
- **NawaDesk MCP server** (`src/nawadesk_mcp/`): tools `get_ticket`, `list_my_tickets` (read) และ `create_ticket`, `add_comment`, `update_ticket_status` (write) พร้อม MCP tool annotations (`readOnlyHint`)
- **ตัวตนผู้ใช้ถูกกำหนดตอนเปิด server** (`NAWADESK_ACTING_EMPLOYEE_ID`) ไม่ใช่ argument ของ tool → โมเดลสวมรอยคนอื่นด้วยการแก้ parameter ไม่ได้ (มี test ตรวจว่าไม่มี tool ไหนรับ employee/user)
- **Human in the loop**: tool อ่านรันทันที · tool เขียนจะหยุดและแสดง preview ให้ผู้ใช้ยืนยันก่อน
- **สิทธิ์ตรวจที่ server เสมอ**: แม้ผู้ใช้กดยืนยัน พนักงานสั่ง "ปิด ticket IT-1042" ก็ได้ `permission denied` (SEC5) · ดู ticket คนอื่นได้คำตอบ "not found" (ไม่บอกว่ามีอยู่)
- การอ่านใช้ทาง row-level security เดียวกับ Data agent → นิยามสิทธิ์มีที่เดียว

### ใช้ NawaDesk กับ Claude Desktop / VS Code
MCP server เป็นมาตรฐานเปิด ใช้กับ client อื่นได้ทันที เช่น `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "nawadesk": {
      "command": "C:\\Users\\Asus\\Desktop\\Resume\\enterprise-copilot\\.venv\\Scripts\\python.exe",
      "args": ["-m", "nawadesk_mcp.server"],
      "env": { "NAWADESK_ACTING_EMPLOYEE_ID": "NT0082" }
    }
  }
}
```
(ต้องเปิด Docker/Postgres ไว้ และ `.env` อยู่ใน root ของ repo)

## ข้อจำกัดที่รู้อยู่ (และแผน)
- Data agent ยังเรียก LLM 2 ครั้งต่อคำถาม (สร้าง SQL + สรุป) — สัปดาห์ 4 orchestrator จะเลือกเรียกเฉพาะ agent ที่จำเป็น
- ตัวตนผู้ใช้ยังเลือกด้วย `--as` — สัปดาห์ 5 เปลี่ยนเป็น login (Entra ID / JWT) และส่ง identity ไป MCP server อย่างปลอดภัย
- ยังไม่มี audit log ของ action ที่ทำผ่าน MCP — สัปดาห์ 5–6 (Langfuse traces)
