"""Input/output guardrails that run in code, before and after any LLM call.

    from copilot.guardrails import check_input, mask_output

check_input(question) does three things, cheapest first:
  1. Length cap — very long inputs are a cost and prompt-stuffing risk.
  2. Prompt-injection pre-check — a small pattern list (EN + TH). Azure's prompt shield is the
     second layer (see llm.ContentFiltered); this layer is free, instant, and works with any model.
  3. PII masking (security test SEC4) — Thai national ID numbers and payment card numbers are
     replaced *before* the text reaches the LLM, the audit log, or a ticket. The model never sees them.

mask_output(text) masks the same PII in answers, in case one ever comes back from data.

Phone numbers and work e-mails are deliberately NOT masked: people legitimately put a call-back
number in an IT ticket, and colleague e-mails are company directory data.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_INPUT_CHARS = 2000

# 1-2345-67890-12-3, 1 2345 67890 12 3 or 1234567890123
_THAI_ID = re.compile(r"(?<![\d-])(\d)[- ]?(\d{4})[- ]?(\d{5})[- ]?(\d{2})[- ]?(\d)(?![\d-])")
# 13-19 digits, optionally grouped by spaces/dashes (checked with Luhn below)
_CARD = re.compile(r"(?<![\d-])\d(?:[- ]?\d){12,18}(?![\d-])")

_INJECTION = [re.compile(p, re.IGNORECASE) for p in (
    r"\b(ignore|disregard|forget|override)\b.{0,30}\b(previous|prior|above|earlier|all|system)\b.{0,20}\b(instruction|prompt|rule|message)s?\b",
    r"\b(reveal|show|print|repeat|output)\b.{0,30}\b(system prompt|hidden instructions?|your instructions)\b",
    r"\byou are now\b|\bdeveloper mode\b|\bjailbreak\b|\bDAN\b",
    r"(ลืม|เพิกเฉย|ไม่ต้องสนใจ|ไม่ต้องทำตาม|ข้าม|ยกเลิก).{0,20}(คำสั่ง|กฎ|ข้อกำหนด|instruction)",
    r"(แสดง|เปิดเผย|บอก|พิมพ์).{0,20}(system prompt|พรอมต์ระบบ|พร้อมต์ระบบ|คำสั่งระบบ|คำสั่งลับ)",
    r"(สวมบทบาท|ทำตัวเป็น|แกล้งเป็น|สมมติว่า(คุณ|เธอ)?เป็น).{0,20}(admin|แอดมิน|ผู้ดูแลระบบ|ไม่มีข้อจำกัด)",
)]

BLOCKED_INJECTION = ("ขออภัยครับ คำถามนี้มีลักษณะพยายามเปลี่ยนคำสั่งหรือข้ามข้อจำกัดของระบบ จึงไม่สามารถดำเนินการได้ "
                     "หากต้องการข้อมูลเรื่อง HR/IT ลองถามตรงๆ ได้เลยครับ")
BLOCKED_TOO_LONG = f"ข้อความยาวเกินไป (เกิน {MAX_INPUT_CHARS} ตัวอักษร) ลองสรุปคำถามให้สั้นลงครับ"

PII_LABEL = {"thai_id": "[เลขบัตรประชาชน]", "card": "[เลขบัตร]"}
PII_NOTICE = {"thai_id": "เลขบัตรประชาชน", "card": "เลขบัตรเครดิต/เดบิต"}


@dataclass
class InputCheck:
    text: str                                   # masked text — the only version that goes further
    blocked: str | None = None                  # reason code: "injection" | "too_long"
    message: str | None = None                  # what to tell the user when blocked
    pii: list[str] = field(default_factory=list)

    @property
    def notice(self) -> str | None:
        if not self.pii:
            return None
        kinds = ", ".join(dict.fromkeys(PII_NOTICE[p] for p in self.pii))
        return f"🔒 ระบบซ่อน{kinds}ที่คุณพิมพ์ไว้แล้ว — ข้อมูลนี้ไม่ถูกส่งให้ AI และไม่ถูกบันทึก ไม่ต้องพิมพ์ข้อมูลส่วนตัวแบบนี้ในแชทครับ"


def thai_id_valid(digits: str) -> bool:
    """Checksum of the 13-digit Thai national ID."""
    if len(digits) != 13 or not digits.isdigit():
        return False
    s = sum(int(d) * (13 - i) for i, d in enumerate(digits[:12]))
    return (11 - s % 11) % 10 == int(digits[12])


def luhn_valid(digits: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digits)):
        n = int(d) * (2 if i % 2 else 1)
        total += n - 9 if n > 9 else n
    return total % 10 == 0


def mask_pii(text: str) -> tuple[str, list[str]]:
    """Return (masked_text, kinds_found). Any 13-digit ID-shaped number is masked even with a bad
    checksum (a typo'd ID is still someone's ID); card numbers must pass Luhn to avoid eating
    ordinary long numbers."""
    found: list[str] = []

    def _id(m: re.Match) -> str:
        found.append("thai_id")
        return PII_LABEL["thai_id"]

    def _card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if luhn_valid(digits):
            found.append("card")
            return PII_LABEL["card"]
        return m.group(0)

    text = _THAI_ID.sub(_id, text)
    text = _CARD.sub(_card, text)
    return text, found


def looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION)


def check_input(text: str) -> InputCheck:
    text = (text or "").strip()
    masked, pii = mask_pii(text)
    if len(text) > MAX_INPUT_CHARS:
        return InputCheck(masked[:200], "too_long", BLOCKED_TOO_LONG, pii)
    if looks_like_injection(masked):
        return InputCheck(masked, "injection", BLOCKED_INJECTION, pii)
    return InputCheck(masked, pii=pii)


def mask_output(text: str) -> str:
    return mask_pii(text or "")[0]
