# services/ingest.py
from typing import Dict, List
from core.text_clean import clean_text
from core.utils import canonicalize_url, humanize_category
from core.formatter import _parse_date
from core.db import init_db, get_conn, upsert_article, reclassify_by_source
from fetchers.rss_fetcher import obtener_noticias_recientes
from fetchers.reddit_fetcher import obtener_de_reddit
from fetchers.youtube_fetcher import obtener_de_youtube

# Mapa en minúsculas (las “agujas” que buscaremos dentro del source)
SRC_MAP = {
    "reddit r/technology": "TECNOLOGIA",
    "reddit r/futurology": "TECNOLOGIA",
    "reddit r/gaming":     "VIDEOJUEGOS",  # o "CULTURA", como prefieras
    "xataka":              "TECNOLOGIA",
    "mit tech review":     "TECNOLOGIA",
    "nasa":                "CIENCIA",
    "wired":               "TECNOLOGIA",
}

def fallback_by_source(src: str) -> str | None:
    s = (src or "").strip().lower()
    for needle, cat in SRC_MAP.items():
        if needle in s:      # ← match parcial e insensible a mayúsculas
            return cat
    return None


def _iso_or_none(v):
    if not v:
        return None
    dt = _parse_date(v)
    return dt.isoformat() if dt else None

def ingest_now() -> Dict[str, int]:
    """Recoge fuentes, normaliza y hace upsert en SQLite. Devuelve contadores."""
    items: List[dict] = []
    items += (obtener_noticias_recientes() or [])
    items += (obtener_de_reddit() or [])
    items += (obtener_de_youtube() or [])

    init_db()
    ins = upd = 0
    skipped = 0
    with get_conn() as conn:
        for it in items:
            title = clean_text(it.get("titulo") or it.get("title") or "")
            url = (it.get("link") or it.get("url") or "").strip()
            can = canonicalize_url(url) if url else ""
            date = _iso_or_none(it.get("fecha") or it.get("date"))
            src = clean_text(it.get("fuente") or it.get("source") or "")
            cat = humanize_category(it.get("categoria") or it.get("category") or "OTROS")

            # Fallback por fuente si sigue en OTROS
            if cat == "OTROS":
                fb = fallback_by_source(src)
                if fb:
                    cat = humanize_category(fb)

            # Saltar registros incompletos (mejor que meter basura)
            if not (title and url and can and date and src):
                skipped += 1
                continue

            # --- Opción A (si tu upsert_article acepta dict + conn) ---
            try:
                rec = {
                    "title": title,
                    "url": url,
                    "canonical_url": can,
                    "date": date,
                    "source": src,
                    "category": cat,
                }
                ok = upsert_article(rec, conn=conn)
            except TypeError:
                # --- Opción B (si espera argumentos nombrados) ---
                ok = upsert_article(
                    conn=conn,
                    title=title,
                    url=url,
                    canonical_url=can,
                    date=date,
                    source=src,
                    category=cat,
                )

            if ok is True or ok == "inserted":
                ins += 1
            else:
                upd += 1

        # ⬇⬇⬇ NUEVO: reclasificar en BD cualquier 'OTROS' reconocible por fuente
        reclass = reclassify_by_source(conn)

    return {
        "collected": len(items),
        "inserted": ins,
        "updated":  upd,
        "skipped":  skipped,
        "reclassified": reclass,   # ⬅ NUEVO
    }


