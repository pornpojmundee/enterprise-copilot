# Azure setup (ทำครั้งเดียว ~20 นาที)

> บัญชีแบบ **Pay-As-You-Go** (จ่ายตามใช้จริง ตัดบัตรรายเดือน) — ถ้าใช้ Azure for Students ดูภาคผนวกท้ายไฟล์
> ตรวจกับเอกสาร Microsoft Learn เมื่อ ต.ค. 2026 — หน้าจอ Azure เปลี่ยนบ่อย ชื่อปุ่มอาจต่างเล็กน้อย
> พอร์ทัลสำหรับ deploy โมเดลชื่อ **Microsoft Foundry** (https://ai.azure.com)

## 0. ค่าใช้จ่าย — อ่านก่อน
- **เสียเงินเฉพาะตอนเรียกใช้โมเดล** คิดตามจำนวน token (คำถาม + เอกสารที่ส่งเข้า + คำตอบที่ได้)
- สร้าง resource / deploy โมเดลแบบ **Global Standard** ทิ้งไว้โดยไม่เรียกใช้ = **$0**
- Azure รวมยอดทั้งเดือนแล้วตัดบัตรตอนสิ้นรอบ — ดูยอดสะสมได้ตลอดที่ **Cost Management → Cost analysis**
- โปรเจคนี้ใช้โมเดล mini ค่าใช้จ่ายจริงราว **$5–20 ทั้งโปรเจค** (ช่วงที่ใช้มากสุดคือรัน eval สัปดาห์ 6)
- ข้อมูลทั้งหมดของโปรเจค (โค้ด, ฐานข้อมูล, เอกสาร) อยู่บน GitHub และเครื่องคุณ — บน Azure มีแค่ "ทางเข้า" ไปยังโมเดล

### ⚠️ สิ่งที่คิดเงินรายชั่วโมงแม้ไม่ได้ใช้ — ห้ามสร้าง
| อย่าเลือก / อย่าสร้าง | เพราะ |
|---|---|
| Deployment type **Provisioned (PTU)** | คิดเงินรายชั่วโมงตลอดเวลา — ใช้ **Global Standard** เท่านั้น |
| **Fine-tuning** / deploy โมเดลที่ fine-tune เอง | ค่าฝากโมเดลรายชั่วโมง |
| Azure AI Search, Virtual Machine, Azure Database, App Service plan | คิดเงินรายชั่วโมง — โปรเจคนี้ใช้ Postgres ใน Docker บนเครื่องแทน |
| สร้าง resource นอก resource group `rg-enterprise-copilot` | จะตามลบ/ตรวจยาก |

## 1. ตั้ง budget alert (ทำก่อนสร้างอะไร)
1. Portal (https://portal.azure.com) → ค้นหา **Cost Management** → **Budgets** → **+ Add**
2. Scope: subscription ของคุณ · Reset period: **Monthly** · Amount: `10` USD
3. Alert conditions: **Actual 50%**, **Actual 80%**, **Actual 100%** และ **Forecasted 100%** → อีเมลของคุณ
4. **Create**

> หมายเหตุ: budget **แจ้งเตือนอย่างเดียว ไม่ได้หยุดการใช้เงิน** — ตัวกันเงินจริงคือขั้นที่ 3 (จำกัด TPM) และการดูแล key ในขั้นที่ 6

## 2. สร้าง Azure OpenAI resource
1. Portal → **Create a resource** → ค้นหา **Azure OpenAI** → **Create**
2. **Resource group**: Create new → `rg-enterprise-copilot`
3. **Region**: **East US 2** หรือ **Sweden Central** (มีโมเดลให้เลือกครบที่สุด)
4. **Name**: `aoai-copilot-pornpoj` (ต้องไม่ซ้ำทั่วโลก ถ้าซ้ำให้เติมตัวเลขท้าย)
5. **Pricing tier**: **Standard S0** → Network: **All networks** → **Review + create** → **Create**
6. รอจนขึ้น "Your deployment is complete" — **ขั้นนี้ไม่เสียเงิน**

## 3. Deploy โมเดล (พร้อมเพดานความเร็ว)
1. เปิด resource → **Go to Foundry portal**
2. **Deployments** (หรือ **Models + endpoints**) → **+ Deploy model** → **Deploy base model**
3. เลือก **gpt-5-mini** (ถ้าไม่มี ใช้ `gpt-4.1-mini`) → **Confirm**
4. กด **Customize** แล้วตั้ง:
   - **Deployment name**: `gpt-5-mini` — โค้ดเรียกด้วยชื่อนี้ ไม่ใช่ชื่อโมเดล
   - **Deployment type**: **Global Standard** ⚠️ ห้ามเลือก Provisioned
   - **Tokens per Minute Rate Limit**: ลดลงเหลือ **10K–20K** — พอสำหรับ dev และเป็นเพดานกันโค้ดวนลูปเรียกโมเดลจนเงินไหล
5. **Deploy** แล้วรอสถานะ **Succeeded** — **ขั้นนี้ยังไม่เสียเงิน** จนกว่าจะเรียกใช้

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
3. **ห้าม** commit `.env` (อยู่ใน `.gitignore` แล้ว) หรือส่ง key ให้ใคร รวมถึงในแชทและภาพหน้าจอ

## 5. ทดสอบ
```powershell
.venv\Scripts\activate
python scripts\check_setup.py
```
ทุกบรรทัดควรขึ้น `[OK]` รวมถึง `LLM reply: 'OK'` (การทดสอบนี้ใช้ไม่ถึง 1 สตางค์)

| Error | สาเหตุที่พบบ่อย |
|---|---|
| `AuthenticationError` | KEY ผิด หรือมีช่องว่างติดมา |
| `NotFoundError` | `LLM_BASE_URL` ไม่ได้ลงท้ายด้วย `/openai/v1/` หรือ `LLM_CHAT_MODEL` ไม่ตรงกับ deployment name |
| `RateLimitError` | ยิงเร็วเกิน TPM ที่ตั้งไว้ (รอสักครู่) หรือ quota เป็น 0 → ดูหัวข้อด้านล่าง |
| `APIConnectionError` | endpoint ผิด หรืออินเทอร์เน็ต |

## 6. ดูแลค่าใช้จ่ายระหว่างทำโปรเจค
- **สัปดาห์ละครั้ง**: เปิด **Cost Management → Cost analysis** ดูยอดเดือนนี้ — ควรอยู่หลักไม่กี่ดอลลาร์
- เห็นยอดผิดปกติ → ไปที่ resource → **Keys and Endpoint** → **Regenerate Key 1** ทันที (key เก่าใช้ไม่ได้อีก) แล้วค่อยหาสาเหตุ
- ใช้ resource group `rg-enterprise-copilot` อันเดียวสำหรับทุกอย่างในโปรเจคนี้

## 7. เมื่อทำโปรเจคเสร็จ / พักโปรเจค
**ปล่อยไว้ได้เลย** — deployment แบบ Global Standard ที่ไม่มีใครเรียก = $0 ต่อเดือน แต่ทำ 2 อย่างนี้:
1. **Regenerate Key 1 และ Key 2** (กันกรณี key หลุดแล้วมีคนแอบใช้) — วันไหนจะใช้ใหม่ค่อยคัดลอก key ใหม่ใส่ `.env`
2. เก็บ budget alert ไว้ — ถ้ามีเงินไหลโดยไม่ตั้งใจจะได้รู้ทันที

ถ้าอยากปิดแบบ 100%: ลบ resource group `rg-enterprise-copilot` → ทุกอย่างบน Azure หายและหยุดคิดเงินแน่นอน
ข้อมูลโปรเจคไม่หาย (อยู่บน GitHub และเครื่องคุณ) — เปิดใหม่ภายหลังได้ด้วยขั้นที่ 2–4 ใช้เวลาราว 10 นาที

---

## ถ้าไม่มี quota (0 TPM)
1. **ลอง region อื่น** — สร้าง resource ใหม่ใน East US 2 / Sweden Central / East US แล้ว deploy อีกครั้ง
2. **ลองโมเดลอื่น** — `gpt-4.1-mini` หรือ `gpt-4o-mini`
3. **ใช้ผู้ให้บริการอื่นที่รองรับ OpenAI-compatible API** ไปก่อน — โค้ดไม่ผูกกับ Azure แค่เปลี่ยน 3 บรรทัดใน `.env`
   แล้วค่อยย้ายกลับมา Azure ตอน deploy (สัปดาห์ 7)

ไม่ว่าเลือกทางไหน ใน README ให้เขียนว่าออกแบบให้ **provider-agnostic** — เป็นจุดที่กรรมการสัมภาษณ์ชอบ

## ภาคผนวก: บัญชีแบบอื่น
- **Azure free account** — เครดิต $200 ภายใน 30 วัน หลังจากนั้นต้องอัปเกรดเป็น Pay-As-You-Go (เติมเครดิตไม่ได้) ดูเครดิตที่ Cost Management + Billing → Billing profile → Azure credits — ถ้าไม่มีเมนูนี้แปลว่าบัญชีไม่มีเครดิต
- **Azure for Students** — $100 ใช้ได้ 12 เดือน ไม่ต้องใช้บัตร สมัครที่ https://azure.microsoft.com/free/students ด้วยอีเมลนักศึกษา
  ถูกจำกัด region: Portal → **Policy** → **Assignments** → "Allowed resource deployment regions" แล้วเลือก region จากรายการนั้นในขั้นที่ 2

## อ้างอิง
- Create resource & deploy model: https://learn.microsoft.com/azure/ai-foundry/openai/how-to/create-resource
- v1 API (OpenAI client + /openai/v1/): https://learn.microsoft.com/azure/foundry/openai/api-version-lifecycle
- Quotas and limits: https://learn.microsoft.com/azure/foundry/openai/quotas-limits
- Budgets: https://learn.microsoft.com/azure/cost-management-billing/costs/tutorial-acm-create-budgets
