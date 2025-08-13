from __future__ import annotations
import html, re, unicodedata
from ftfy import fix_text
from typing import Optional

# Quita un 'â' espurio antes de sub/superscripts: p.ej. NOâ₂ -> NO₂
_SUB_SUP_STRAY_A = re.compile(r'â(?=[₀-₉⁰-⁹])')

def clean_text(s: Optional[str]) -> str:
    if not s:
        return ""
    t = fix_text(str(s))          # repara mojibake común
    t = html.unescape(t)          # &amp; -> &, etc.
    t = _SUB_SUP_STRAY_A.sub("", t)
    t = unicodedata.normalize("NFC", t)   # normaliza Unicode
    t = " ".join(t.split())       # espacios
    return t.strip()