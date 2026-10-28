# Demo personas

สร้างอัตโนมัติโดย `scripts/generate_seed.py` — อย่าแก้ไฟล์นี้เอง
วันที่ "วันนี้" ในโลกจำลอง: **2026-10-28**

| Persona | Employee ID | ชื่อ | ตำแหน่ง | ทีม | app_role | หัวหน้า | ใช้ใน |
|---|---|---|---|---|---|---|---|
| employee | `NT0082` | พิมพ์ชนก ศรีสวัสดิ์ (Ploy) | Data Engineer | DATA-DE | employee | NT0031 Nattawut | UC1, UC2, SEC1, SEC5 |
| new_hire | `NT0197` | ธนกร วงศ์ใหญ่ (Ton) | Sales Executive | SALES-SMB | employee | NT0037 Somchai | UC3 |
| data_lead | `NT0031` | ณัฐวุฒิ ทองดี (Nat) | Data Engineering Lead | DATA-DE | team_lead | NT0098 Thidarat | UC4, SEC2 |
| it_support | `NT0048` | สุภาพร แก้วมณี (Fon) | IT Support Specialist | IT-SD | it_support | NT0063 Benjamas | UC5 |
| admin | `NT0016` | วรวุฒิ ชัยมงคล (Wut) | Infrastructure & Security Lead | IT-INF | admin | NT0058 Chaiwat | UC6 |
| hr | `NT0061` | กมลชนก บุญมา (Kwan) | HR Officer | HR-OPS | hr | NT0043 Pakorn | HR view |
| ceo | `NT0001` | อรรถพล นาวาวงศ์ (Aek) | Chief Executive Officer | - | executive | - | Executive view |

## ข้อเท็จจริงที่ use case อ้างอิง (ใช้ตรวจคำตอบใน eval)
- **employee (Ploy)**: ลาพักร้อนปี 2026 สิทธิ์ 10 วัน ใช้ไป 8.5 วัน **เหลือ 1.5 วัน**
- UC1: ลาศุกร์ 4 ธ.ค. 2026 + จันทร์ 7 ธ.ค. เป็นวันหยุดชดเชยวันพ่อ → **นับลา 1 วัน** → เหลือพอ
- **new_hire (Ton)**: อยู่ระหว่างทดลองงาน → ยังไม่มีสิทธิ์ลาพักร้อน
- **IT-1042**: notebook ของ Ploy เปิดไม่ติดหลังอัปเดต BIOS (P2, waiting) มอบหมายให้ Fon
- **data_lead (Nat)**: ทีม DATA-DE มี ticket ค้างที่เกิน SLA (ดู `itsm.v_ticket_sla`)
