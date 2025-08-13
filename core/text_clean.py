# core/text_clean.py
from __future__ import annotations
import html
from ftfy import fix_text
from typing import Optional

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    t = fix_text(str(s))          # arregla mojibake: canâ€™t -> can’t
    t = html.unescape(t)          # &amp; -> &, &quot; -> "
    t = " ".join(t.split())       # espacios normalizados
    return t.strip()