# Azure setup (ทำครั้งเดียว ~20–30 นาที)

> ตรวจกับเอกสาร Microsoft Learn เมื่อ ต.ค. 2026 — หน้าจอ Azure เปลี่ยนบ่อย ชื่อปุ่มอาจต่างเล็กน้อย
> พอร์ทัลสำหรับ deploy โมเดลตอนนี้ชื่อ **Microsoft Foundry** (https://ai.azure.com) มีทั้งแบบ "New" และ "Classic"

## 1. สมัครบัญชี Azure
มี 2 แบบ เลือกแบบเดียว:
- **Azure free account** — เครดิต $200 ใช้ภายใน 30 วัน (ต้องใช้บัตรยืนยันตัวตน) หลังจากนั้นต้องอัปเกรดเป็น Pay-As-You-Go จึงจะใช้ต่อได้ เครดิตที่เหลือจะหมดอายุ
  อัปเกรดก่อนครบ 30 วันได้โดยไม่เสียเครดิตที่เหลือ — โปรเจคนี้ใช้จริงราว $5–20 ทั้งโปรเจค
- **Azure for Students** — $100 ใช้ได้ 12 เดือน ไม่ต้องใช้บัตร แต่จำกัด region/quota (ขั้นตอนด้านล่าง)

### Azure for Students
1. ไปที่ https://azure.microsoft.com/free/students → **Start free** → ล็อกอินด้วยอีเมลนักศึกษา
2. ยืนยันตัวตน (ไม่ต้องใช้บัตรเครดิต)
3. https://portal.azure.com → ค้นหา **Subscriptions** → ต้องเห็น "Azure for Students" และเครดิต $100

## 2. ตั้ง budget alert (ทำก่อนสร้างอะไร)
Portal → **Cost Management** → **Budgets** → **Add** → Amount `10` USD, แจ้งเตือนที่ 50% / 80% / 100%

## 3. ดูว่า subscription นี้ใช้ region ไหนได้ (เฉพาะ Azure for Students — free account ข้ามได้ แนะนำ East US 2 หรือ Sweden Central)
Azure for Students ถูกจำกัดให้สร้าง resource ได้ไม่กี่ region (มักราว 5 region)
1. Portal → **Policy** → **Assignments** → เปิด policy ที่ชื่อคล้าย "Allowed resource deployment regions"
2. จด region ที่อนุญาตไว้ — ขั้นต่อไปต้องเลือกจากรายการนี้เท่านั้น
   ถ้าเลือก region อื่น จะเจอ error "policy violation"

## 4. สร้าง Azure OpenAI resource
1. Portal → **Create a resource** → ค้นหา **Azure OpenAI** → **Create**
2. Resource group: สร้างใหม่ชื่อ `rg-enterprise-copilot`
3. Region: เลือกจาก region ที่อนุญาตในขั้นที่ 3
4. Name: `aoai-copilot-<ชื่อคุณ>` (ต้องไม่ซ้ำทั่วโลก)
5. Pricing tier: **Standard S0** → Network: **All networks** → Review + create

## 5. เช็ก quota ก่อน deploy (สำคัญสำหรับ student)
1. เปิด https://ai.azure.com → เลือก resource ของคุณ
2. ไปที่ **Quota** (หรือ **Management center → Quota**)
3. ดูว่าโมเดล mini (เช่น `gpt-5-mini`, `gpt-4.1-mini`, `gpt-4o-mini`) ใน region ของคุณมี quota มากกว่า **0 TPM** หรือไม่
   - **มี quota** → ไปขั้นที่ 6
   - **0 TPM ทุกโมเดล** → ข้ามไปหัวข้อ "ถ้าไม่มี quota" ด้านล่าง

## 6. Deploy โมเดล
1. ใน Foundry → **Deployments** (หรือ **Models + endpoints**) → **+ Deploy model** → **Deploy base model**
2. เลือกโมเดล mini ที่มี quota → **Confirm**
3. **Deployment name**: ตั้งให้จำง่าย เช่น `gpt-5-mini` — โค้ดจะเรียกด้วยชื่อนี้ ไม่ใช่ชื่อโมเดล
4. **Deployment type**: Global Standard (ถ้าเลือกได้) หรือ Standard
5. รอสถานะเป็น **Succeeded**

## 7. ใส่ค่าใน .env (ทำเองบนเครื่องคุณ)
1. Resource → **Keys and Endpoint** → คัดลอก **Endpoint** และ **KEY 1**
2. `cp .env.example .env` แล้วแก้:
   ```
   LLM_BASE_URL=https://<resource-name>.openai.azure.com/openai/v1/
   LLM_API_KEY=<KEY 1>
   LLM_CHAT_MODEL=<deployment name จากขั้นที่ 6>
   ```
   ต่อท้าย endpoint ด้วย `/openai/v1/` — เป็น API แบบใหม่ (v1) ที่ไม่ต้องระบุ `api-version`
3. **ห้าม** commit `.env` หรือส่ง key ให้ใคร

## 8. ทดสอบ
```bash
docker compose up -d
python scripts/check_setup.py
```
ทุกบรรทัดควรขึ้น `[OK]`

---

## ถ้าไม่มี quota (0 TPM)
ปัญหานี้พบบ่อยกับ Azure for Students — ไม่ใช่ความผิดของคุณ ทางเลือก:

1. **รอ/เช็กอีเมลจาก Microsoft** — บาง subscription ได้รับการอัปเกรด AI quota tier (Free → Tier 1) อัตโนมัติหลังใช้งานไปสักพัก
2. **สร้าง subscription แบบ Pay-As-You-Go แยก** ใช้เฉพาะ Azure OpenAI (ต้องใช้บัตร)
   - ตั้ง budget alert $5–10 ทันที
   - โปรเจคนี้ใช้จริงราว $5–20 ทั้งโปรเจค
3. **ใช้ผู้ให้บริการอื่นที่รองรับ OpenAI-compatible API** — โค้ดโปรเจคนี้ไม่ผูกกับ Azure แค่เปลี่ยน 3 บรรทัดใน `.env`
   (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_CHAT_MODEL`) แล้วค่อยย้ายกลับมา Azure ตอน deploy

ไม่ว่าเลือกทางไหน ใน README ให้เขียนว่าออกแบบให้ **provider-agnostic** — เป็นจุดที่กรรมการสัมภาษณ์ชอบ

## อ้างอิง
- Create resource & deploy model: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/create-resource
- v1 API (OpenAI client + /openai/v1/): https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle
- Quotas and limits: https://learn.microsoft.com/azure/foundry/openai/quotas-limits
