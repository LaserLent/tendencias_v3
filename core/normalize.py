# core/normalize.py
from __future__ import annotations
from typing import Optional, Dict
from core.utils import canonicalize_url

def to_canonical(rec: dict) -> Optional[Dict[str, str]]:
    # Acepta claves ES/EN y devuelve EN canónico
    if not isinstance(rec, dict): 
        return None
    title = (rec.get("title") or rec.get("titulo") or "").strip()
    url   = (rec.get("url")   or rec.get("link")   or "").strip()
    date  = (rec.get("date")  or rec.get("fecha")  or "").strip()
    src   = (rec.get("source")or rec.get("fuente") or "").strip()
    cat   =  rec.get("category") or rec.get("categoria")
    if not (title and url and date and src):
        return None
    try:
        can = canonicalize_url(url) or url
    except Exception:
        can = url
    return {
        "title": title,
        "url": url,
        "canonical_url": can,
        "date": date,
        "source": src,
        "category": cat if (cat is None or isinstance(cat, str)) else str(cat),
    }