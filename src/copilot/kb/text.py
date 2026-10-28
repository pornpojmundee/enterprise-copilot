"""Thai-aware tokenization for BM25.

Thai has no spaces between words, so a plain `.split()` would treat a whole sentence as
one token and keyword search would never match. PyThaiNLP's dictionary-based `newmm`
tokenizer splits it into words; English/numbers pass through lower-cased.
"""
from __future__ import annotations

import re
from functools import lru_cache

from pythainlp.tokenize import word_tokenize

_KEEP = re.compile(r"[\w฀-๿]")  # at least one letter/digit/Thai char
# Very common Thai/English function words that add noise to keyword matching.
STOPWORDS = {
    "ที่", "และ", "หรือ", "ของ", "ใน", "ได้", "ให้", "เป็น", "การ", "จะ", "ไม่", "มี", "ก็", "ว่า",
    "the", "a", "an", "of", "to", "and", "or", "is", "in", "for",
    "ครับ", "ค่ะ", "คะ", "นะ", "ไหม", "บ้าง", "อะไร", "ยังไง", "อย่างไร",
}


@lru_cache(maxsize=4096)
def tokenize(text: str) -> tuple[str, ...]:
    out = []
    for tok in word_tokenize(text.lower(), engine="newmm", keep_whitespace=False):
        tok = tok.strip()
        if tok and _KEEP.search(tok) and tok not in STOPWORDS:
            out.append(tok)
    return tuple(out)
