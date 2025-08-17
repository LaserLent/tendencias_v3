# services/ingest.py
from __future__ import annotations
from typing import Dict, List, Optional
from pathlib import Path
import json
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin


from core.text_clean import clean_text
from core.utils import canonicalize_url, humanize_category
from core.formatter import _parse_date
from core.db import init_db, get_conn, upsert_article, reclassify_by_source
from fetchers import rss_fetcher, reddit_fetcher, youtube_fetcher

# --------------------------------------------------------------------------------------
# Mapeo de fuente -> categoría por defecto (prioritario frente a sources.json)
# --------------------------------------------------------------------------------------
SRC_MAP = {
    "reddit r/technology": "TECNOLOGIA",
    "reddit r/futurology": "TECNOLOGIA",
    "reddit r/gaming":     "VIDEOJUEGOS",  # o "CULTURA", como prefieras
    "xataka":              "TECNOLOGIA",
    "mit tech review":     "TECNOLOGIA",
    "nasa":                "CIENCIA",
    "wired":               "TECNOLOGIA",
}

# --------------------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------------------
SOURCES_PATH = Path(__file__).resolve().parents[1] / "data" / "sources.json"


def load_sources() -> List[dict]:
    """
    Carga el registro dinámico de fuentes desde data/sources.json.
    Devuelve una lista de dicts con claves: name, type, url, category, enabled, interval_minutes.
    Filtra las deshabilitadas.
    """
    try:
        if not SOURCES_PATH.exists():
            return []
        data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        items = data.get("sources", []) if isinstance(data, dict) else data
        out: List[dict] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            if not it.get("enabled", True):
                continue
            name = (it.get("name") or "").strip()
            stype = (it.get("type") or "").strip().lower()  # "rss", "subreddit", "youtube", etc.
            url = (it.get("url") or "").strip()
            category = (it.get("category") or "OTROS").strip().upper()
            interval = int(it.get("interval_minutes") or 30)
            if name and stype and url:
                out.append({
                    "name": name,
                    "type": stype,
                    "url": url,
                    "category": category,
                    "interval_minutes": interval,
                })
        return out
    except Exception as e:
        print(f"[WARN] load_sources() failed: {e}")
        return []


def fallback_by_source(src: str) -> Optional[str]:
    s = (src or "").strip().lower()
    for needle, cat in SRC_MAP.items():
        if needle in s:      # match parcial e insensible a mayúsculas
            return cat
    return None


def _iso_or_none(v: Optional[str]) -> Optional[str]:
    if not v:
        return None
    dt = _parse_date(v)
    return dt.isoformat() if dt else None


def _fetch_rss_items_simple(url: str):
    """Descarga y parsea RSS/Atom. Devuelve dicts con title, url, date (ISO si existe)."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read()

    root = ET.fromstring(data)

    # ---- RSS 2.0 -----------------------------------------------------------
    channel = root.find("./channel")
    if channel is not None:
        for item in channel.findall("./item"):
            title = (item.findtext("title") or "").strip()
            link  = (item.findtext("link") or "").strip()
            pub   = (item.findtext("pubDate")
                     or item.findtext("{http://purl.org/dc/elements/1.1/}date")
                     or "").strip()

            # Normaliza fecha a ISO (usa tu parser cuando sea posible)
            iso = _iso_or_none(pub)
            if not iso and pub:
                try:
                    iso = parsedate_to_datetime(pub).isoformat()
                except Exception:
                    iso = None

            # Enlaces relativos → absolutos
            if link and not link.lower().startswith(("http://", "https://")):
                link = urljoin(url, link)

            if title and link:
                yield {"title": title, "url": link, "date": iso}
        return

    # ---- Atom --------------------------------------------------------------
    ATOM = "{http://www.w3.org/2005/Atom}"
    for entry in root.findall(f".//{ATOM}entry"):
        title = (entry.findtext(f"{ATOM}title") or "").strip()

        # link rel="alternate" o el primero disponible
        link_el = entry.find(f"{ATOM}link[@rel='alternate']") or entry.find(f"{ATOM}link")
        link = (link_el.get("href") if link_el is not None else "").strip()

        pub = (entry.findtext(f"{ATOM}updated")
               or entry.findtext(f"{ATOM}published")
               or "").strip()

        iso = _iso_or_none(pub)
        if not iso and pub:
            try:
                iso = parsedate_to_datetime(pub).isoformat()
            except Exception:
                iso = None

        if link and not link.lower().startswith(("http://", "https://")):
            link = urljoin(url, link)

        if title and link:
            yield {"title": title, "url": link, "date": iso}



# --------------------------------------------------------------------------------------
# Ingesta dinámica (sources.json) — versión única y canónica
# --------------------------------------------------------------------------------------

def ingest_from_dynamic_sources() -> Dict[str, int]:
    """
    Lee data/sources.json y hace upsert en SQLite de las fuentes dinámicas.
    Soporta type='rss' (extensible). Normaliza al mismo esquema que ingest_now().

    Reglas clave:
    - Dedupe por canonical_url (lo gestiona upsert_article en core.db).
    - Categoría: prioriza SRC_MAP[name] y, si no existe, usa la categoría del JSON.
    - source_type: se persiste (p.ej., 'rss').
    """
    init_db()
    sources = load_sources()
    if not sources:
        print("[INFO] No hay fuentes dinámicas habilitadas en data/sources.json")
        return {"sources": 0, "collected": 0, "inserted": 0, "updated": 0, "skipped": 0, "failed": 0, "reclassified": 0}

    total_in = ins = upd = skipped = failed = 0
    used_sources = 0

    with get_conn() as conn:
        for src in sources:
            name = (src.get("name") or "?").strip()
            stype = (src.get("type") or "").lower().strip()
            url = (src.get("url") or "").strip()

            # Categoría: **prioriza** SRC_MAP; si no, la del JSON
            category = (SRC_MAP.get(name.lower(), (src.get("category") or "OTROS"))).strip().upper()

            if stype != "rss":
                print(f"[SKIP] {name}: type={stype!r} no soportado todavía en dinámicas")
                continue
            if not url:
                print(f"[WARN] {name}: sin URL")
                continue

            used_sources += 1
            print(f"[INFO] Ingeriendo {name} (rss) → {url}")
            try:
                for raw in _fetch_rss_items_simple(url):
                    total_in += 1

                    # Normalización alineada con ingest_now()
                    title = clean_text(raw.get("title") or "")
                    link  = (raw.get("url") or "").strip()
                    can   = canonicalize_url(link) if link else ""
                    date  = raw.get("date") or ""
                    src_h = clean_text(name)
                    cat_h = humanize_category(category)

                    # Saltar registros incompletos (como en ingest_now)
                    if not (title and link and can and date and src_h):
                        skipped += 1
                        continue

                    rec = {
                        "title": title,
                        "url": link,
                        "canonical_url": can,
                        "date": date,
                        "source": src_h,
                        "category": cat_h,
                        "source_type": stype,
                    }

                    try:
                        ok = upsert_article(rec, conn=conn)
                    except TypeError:
                        ok = upsert_article(conn=conn, **rec)

                    if ok is True or ok == "inserted":
                        ins += 1
                    else:
                        upd += 1

            except Exception as e:
                failed += 1
                print(f"[ERROR] Ingesta falló para {name}: {e}")

        # Reclasificación final por si quedaron 'OTROS' reconocibles
        try:
            reclassified = reclassify_by_source(conn)
        except Exception:
            reclassified = 0

    print(f"[INFO] Dynamic sources: sources_used={used_sources} in={total_in} inserted={ins} updated={upd} skipped={skipped} failed={failed} reclassified={reclassified}")
    return {
        "sources": used_sources,
        "collected": total_in,
        "inserted": ins,
        "updated": upd,
        "skipped": skipped,
        "failed": failed,
        "reclassified": reclassified,
    }


# --------------------------------------------------------------------------------------
# Ingesta "builtins" (fetchers internos: Reddit, YouTube y algún RSS propio)
# --------------------------------------------------------------------------------------

def ingest_now() -> Dict[str, int]:
    items: List[dict] = []

    # RSS
    rss_items = (rss_fetcher.obtener_noticias_recientes() or [])
    for it in rss_items:
        it.setdefault("source_type", "rss")
    items += rss_items

    # Reddit
    reddit_items = (reddit_fetcher.obtener_de_reddit() or [])
    for it in reddit_items:
        it.setdefault("source_type", "subreddit")
    items += reddit_items

    # YouTube
    yt_items = (youtube_fetcher.obtener_de_youtube() or [])
    for it in yt_items:
        it.setdefault("source_type", "youtube")
    items += yt_items

    init_db()
    ins = upd = skipped = 0
    with get_conn() as conn:
        for it in items:
            title = clean_text(it.get("titulo") or it.get("title") or "")
            url   = (it.get("link") or it.get("url") or "").strip()
            can   = canonicalize_url(url) if url else ""
            date  = _iso_or_none(it.get("fecha") or it.get("date"))
            src   = clean_text(it.get("fuente") or it.get("source") or "")
            cat   = humanize_category(it.get("categoria") or it.get("category") or "OTROS")

            if cat == "OTROS":
                fb = fallback_by_source(src)
                if fb:
                    cat = humanize_category(fb)

            if not (title and url and can and date and src):
                skipped += 1
                continue

            # ✅ usa la etiqueta del fetcher y deja la heurística como fallback
            ls = (src or "").lower()
            lu = (url or "").lower()
            stype = (it.get("source_type") or
                     ("subreddit" if ("reddit" in ls or "reddit.com" in lu) else
                      "youtube"   if ("youtube" in ls or "youtu" in lu)      else
                      "rss"))

            rec = {
                "title": title,
                "url": url,
                "canonical_url": can,
                "date": date,
                "source": src,
                "category": cat,
                "source_type": stype,
            }
            try:
                ok = upsert_article(rec, conn=conn)
            except TypeError:
                ok = upsert_article(conn=conn, **rec)

            if ok is True or ok == "inserted":
                ins += 1
            else:
                upd += 1

        reclass = reclassify_by_source(conn)

    return {"collected": len(items), "inserted": ins, "updated": upd, "skipped": skipped, "reclassified": reclass}


# --------------------------------------------------------------------------------------
# Orquestador único y CLI
# --------------------------------------------------------------------------------------

from typing import Dict

def ingest(mode: str = "both") -> Dict[str, int]:
    """
    Orquesta la ingesta desde distintos orígenes con una sola llamada.

    mode:
      - "builtins": usa los fetchers internos (reddit/youtube/rss integrados en ingest_now)
      - "dynamic" : usa data/sources.json (ingest_from_dynamic_sources)
      - "both"    : hace ambas (por defecto)

    Devuelve contadores agregados y añade:
      - failed_dynamic: nº de fuentes dinámicas que fallaron
      - sources_dynamic: nº de fuentes dinámicas utilizadas
    """
    stats_total: Dict[str, int] = {
        "collected": 0,
        "inserted": 0,
        "updated": 0,
        "skipped": 0,
        "reclassified": 0,
        "failed_dynamic": 0,
        "sources_dynamic": 0,
    }

    # --- builtins (fetchers internos) ---
    if mode in ("builtins", "both"):
        try:
            s = ingest_now()
            for k in ("collected", "inserted", "updated", "skipped", "reclassified"):
                stats_total[k] += int(s.get(k, 0) or 0)
        except Exception as e:
            print(f"[WARN] ingest_now() falló: {e}")

    # --- dynamic (sources.json) ---
    if mode in ("dynamic", "both"):
        try:
            d = ingest_from_dynamic_sources()
            for k in ("collected", "inserted", "updated", "skipped", "reclassified"):
                stats_total[k] += int(d.get(k, 0) or 0)
            # Métricas específicas de dinámicas
            stats_total["failed_dynamic"]  += int(d.get("failed", 0) or 0)
            stats_total["sources_dynamic"] += int(d.get("sources", 0) or 0)
        except Exception as e:
            print(f"[WARN] ingest_from_dynamic_sources() falló: {e}")

    return stats_total


if __name__ == "__main__":
    import sys
    mode = (sys.argv[1] if len(sys.argv) > 1 else "both").lower()
    stats = ingest(mode)
    print(json.dumps({"mode": mode, **stats}, ensure_ascii=False, indent=2))
