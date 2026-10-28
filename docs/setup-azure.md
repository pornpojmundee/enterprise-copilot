# Azure setup (ทำครั้งเดียว ~20 นาที)

> เขียนสำหรับ **Azure free account** (เครดิต $200 / 30 วัน) — ถ้าใช้ Azure for Students ดูภาคผนวกท้ายไฟล์
> ตรวจกับเอกสาร Microsoft Learn เมื่อ ต.ค. 2026 — หน้าจอ Azure เปลี่ยนบ่อย ชื่อปุ่มอาจต่างเล็กน้อย
> พอร์ทัลสำหรับ deploy โมเดลชื่อ **Microsoft Foundry** (https://ai.azure.com)

## 0. เครดิตและค่าใช้จ่าย (อ่านก่อน)
- เครดิต **$200 ใช้ได้ภายใน 30 วัน** นับจากวันสมัคร หรือจนกว่าจะใช้หมด (แล้วแต่อย่างไหนถึงก่อน) ส่วนที่ไม่ได้ใช้จะหายไป **เติมเครดิตเพิ่มไม่ได้**
- หลังจากนั้นต้อง **อัปเกรดเป็น Pay-As-You-Go** (จ่ายตามใช้จริง ตัดบัตรรายเดือน) ไม่งั้น subscription และ resource จะถูกปิด
- อัปเกรดก่อนครบ 30 วันได้ — เครดิตที่เหลือยังใช้ได้จนถึงวันที่ 30
- โปรเจคนี้ใช้โมเดล mini ค่าใช้จ่ายจริงราว **$5–20 ทั้งโปรเจค** → โปรเจค 8 สัปดาห์ จะต้องอัปเกรดราว **สัปดาห์ที่ 4**
- 📌 จดวันหมดอายุเครดิตไว้: Portal → **Subscriptions** → เลือก subscription → ดูวันที่เครดิตหมด

## 1. ตั้ง budget alert (ทำก่อนสร้างอะไร)
1. Portal (https://portal.azure.com) → ค้นหา **Cost Management** → **Budgets** → **Add**
2. Amount: `10` USD
3. แจ้งเตือนที่ **50% / 80% / 100%** ไปที่อีเมลของคุณ

## 2. สร้าง Azure OpenAI resource
1. Portal → **Create a resource** → ค้นหา **Azure OpenAI** → **Create**
2. **Resource group**: Create new → `rg-enterprise-copilot`
3. **Region**: **East US 2** หรือ **Sweden Central** (มีโมเดลให้เลือกครบที่สุด)
4. **Name**: `aoai-copilot-pornpoj` (ต้องไม่ซ้ำทั่วโลก ถ้าซ้ำให้เติมตัวเลขท้าย)
5. **Pricing tier**: **Standard S0** → Network: **All networks** → **Review + create** → **Create**
6. รอจนขึ้น "Your deployment is complete"

## 3. Deploy โมเดล
1. เปิด resource → **Go to Foundry portal**
2. **Deployments** (หรือ **Models + endpoints**) → **+ Deploy model** → **Deploy base model**
3. เลือก **gpt-5-mini** (ถ้าไม่มี ใช้ `gpt-4.1-mini`) → **Confirm**
4. **Deployment name**: `gpt-5-mini` — โค้ดเรียกด้วยชื่อนี้ ไม่ใช่ชื่อโมเดล
5. **Deployment type**: **Global Standard**
6. รอสถานะเป็น **Succeeded**

> ถ้า deploy ไม่ได้เพราะ quota เป็น 0 → ดูหัวข้อ "ถ้าไม่มี quota" ด้านล่าง

## 4. ใส่ค่าใน .env (ทำเองบนเครื่องคุณ)
1. กลับไปที่ resource ใน Portal → **Keys and Endpoint** → คัดลอก **Endpoint** และ **KEY 1**
2. เปิดไฟล์ `.env` ในโฟลเดอร์โปรเจค แล้วแก้ 3 บรรทัด:
   ```
   LLM_BASE_URL=https://aoai-copilot-pornpoj.openai.azure.com/openai/v1/
   LLM_API_KEY=<KEY 1>
   LLM_CHAT_MODEL=gpt-5-mini
   ```
   - ใช้ชื่อ resource ที่ตั้งจริงในขั้นที่ 2
   - ต่อท้าย endpoint ด้วย `/openai/v1/` — เป็น API แบบใหม่ (v1) ที่ไม่ต้องระบุ `api-version`
3. **ห้าม** commit `.env` (อยู่ใน `.gitignore` แล้ว) หรือส่ง key ให้ใคร รวมถึงในแชท

## 5. ทดสอบ
```powershell
.venv\Scripts\activate
python scripts\check_setup.py
```
ทุกบรรทัดควรขึ้น `[OK]` รวมถึง `LLM reply: 'OK'`

| Error | สาเหตุที่พบบ่อย |
|---|---|
| `AuthenticationError` | KEY ผิด หรือมีช่องว่างติดมา |
| `NotFoundError` | `LLM_BASE_URL` ไม่ได้ลงท้ายด้วย `/openai/v1/` หรือ `LLM_CHAT_MODEL` ไม่ตรงกับ deployment name |
| `RateLimitError` | quota หมด/เป็น 0 → ดูหัวข้อถัดไป |
| `APIConnectionError` | endpoint ผิด หรืออินเทอร์เน็ต |

## 6. ก่อนเครดิตหมด (ราวสัปดาห์ที่ 4)
1. Portal → **Subscriptions** → เลือก subscription → **Upgrade** (เลือกแบบ Pay-As-You-Go)
2. ตรวจว่า budget alert $10 ยังอยู่
3. resource และ `.env` ใช้ต่อได้เหมือนเดิม ไม่ต้องตั้งค่าใหม่

---

## ถ้าไม่มี quota (0 TPM)
1. **ลอง region อื่น** — สร้าง resource ใหม่ใน East US 2 / Sweden Central / East US แล้ว deploy อีกครั้ง
2. **ลองโมเดลอื่น** — `gpt-4.1-mini` หรือ `gpt-4o-mini`
3. **ใช้ผู้ให้บริการอื่นที่รองรับ OpenAI-compatible API** ไปก่อน — โค้ดไม่ผูกกับ Azure แค่เปลี่ยน 3 บรรทัดใน `.env`
   แล้วค่อยย้ายกลับมา Azure ตอน deploy (สัปดาห์ 7)

ไม่ว่าเลือกทางไหน ใน README ให้เขียนว่าออกแบบให้ **provider-agnostic** — เป็นจุดที่กรรมการสัมภาษณ์ชอบ

## ภาคผนวก: Azure for Students
- $100 ใช้ได้ 12 เดือน ไม่ต้องใช้บัตร สมัครที่ https://azure.microsoft.com/free/students ด้วยอีเมลนักศึกษา
- ถูกจำกัดให้สร้าง resource ได้ไม่กี่ region: Portal → **Policy** → **Assignments** → เปิด "Allowed resource deployment regions" แล้วเลือก region จากรายการนั้นในขั้นที่ 2 (ไม่งั้นเจอ "policy violation")
- quota ของโมเดลมักน้อยหรือเป็น 0 — เช็กใน Foundry → **Quota** ก่อน deploy

## อ้างอิง
- Create resource & deploy model: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/create-resource
- v1 API (OpenAI client + /openai/v1/): https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle
- Quotas and limits: https://learn.microsoft.com/azure/foundry/openai/quotas-limits
- Free account credit & upgrade: https://learn.microsoft.com/azure/cost-management-billing/manage/create-free-services
- Avoid charges with free account: https://learn.microsoft.com/azure/cost-management-billing/manage/avoid-charges-free-account
