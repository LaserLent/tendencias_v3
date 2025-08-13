# core/text_clean.py
from __future__ import annotations
import html
from typing import Optional
from ftfy import fix_text

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    # 1) Arregla mojibake (UTF-8 mal decodificado como cp1252, etc.)
    t = fix_text(str(s))
    # 2) Des-escapa entidades HTML (&amp;, &quot; ...)
    t = html.unescape(t)
    # 3) Espacios en limpio
    t = " ".join(t.split())
    return t.strip()