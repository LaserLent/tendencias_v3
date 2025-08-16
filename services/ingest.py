# services/ingest.py
from typing import Dict, List
from core.text_clean import clean_text
from core.utils import canonicalize_url, humanize_category
from core.formatter import _parse_date
from core.db import init_db, get_conn, upsert_article, reclassify_by_source
from fetchers.rss_fetcher import obtener_noticias_recientes
from fetchers.reddit_fetcher import obtener_de_reddit
from fetchers.youtube_fetcher import obtener_de_youtube
from pathlib import Path
import json
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

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
# --- NUEVO: utilidades de red/parse RSS sin dependencias ---
import urllib.request  # NUEVO
import xml.etree.ElementTree as ET  # NUEVO
from email.utils import parsedate_to_datetime  # NUEVO

# --- NUEVO: utilidades de canonicalización y DB ---
try:  # NUEVO
    from core.utils import canonicalize_url as _canon  # NUEVO
except Exception:  # NUEVO
    def _canon(u: str) -> str:  # NUEVO
        return u  # fallback simple  # NUEVO

from core.db import get_conn  # NUEVO


def _fetch_rss_items_simple(url: str):  # NUEVO
    """
    Descarga y parsea un RSS básico. Devuelve dicts con title, url, date.
    No cubre todos los RSS del mundo, pero vale para NASA/TechCrunch.
    """  # NUEVO
    with urllib.request.urlopen(url, timeout=15) as resp:  # NUEVO
        data = resp.read()  # NUEVO
    root = ET.fromstring(data)  # NUEVO

    # intentamos <channel>/<item> (RSS 2.0)  # NUEVO
    channel = root.find("./channel") or root  # NUEVO
    for item in channel.findall("./item"):  # NUEVO
        title = (item.findtext("title") or "").strip()  # NUEVO
        link = (item.findtext("link") or "").strip()  # NUEVO
        pub = (item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date") or "").strip()  # NUEVO
        # fecha ISO razonable  # NUEVO
        try:  # NUEVO
            dt = parsedate_to_datetime(pub) if pub else None  # NUEVO
            iso = dt.isoformat() if dt else None  # NUEVO
        except Exception:  # NUEVO
            iso = None  # NUEVO
        if title and link:  # NUEVO
            yield {"title": title, "url": link, "date": iso}  # NUEVO


def _insert_article(item: dict):  # NUEVO
    """
    Inserta 1 artículo en SQLite. Dedupe por canonical_url.
    Campos requeridos: title, url, canonical_url, date, source, category.
    """  # NUEVO
    title = (item.get("title") or "").strip()  # NUEVO
    url = (item.get("url") or "").strip()  # NUEVO
    can = (item.get("canonical_url") or _canon(url) or "").strip()  # NUEVO
    date = item.get("date") or ""  # NUEVO
    source = (item.get("source") or "").strip()  # NUEVO
    category = (item.get("category") or "OTROS").strip().upper()  # NUEVO
    if not (title and url and can and source):  # NUEVO
        return 0  # skip  # NUEVO
    with get_conn() as conn:  # NUEVO
        conn.execute(
            "INSERT OR IGNORE INTO articles (title, url, canonical_url, date, source, category) VALUES (?, ?, ?, ?, ?, ?)",
            (title, url, can, date, source, category),
        )  # NUEVO
    return 1  # NUEVO


# --- NUEVO: conecta el type='rss' al fetcher e inserta en DB ---
def ingest_from_dynamic_sources():  # REDEFINE la función del paso anterior
    """
    Lee data/sources.json y:
      - Para cada fuente habilitada type='rss', descarga items,
      - Enriquecemos con source/category del sources.json,
      - Insertamos en SQLite (INSERT OR IGNORE por canonical_url).
    """  # NUEVO
    sources = load_sources()  # existente
    if not sources:
        print("[INFO] No hay fuentes dinámicas habilitadas en data/sources.json")
        return

    total_in = total_ok = total_err = 0  # NUEVO
    for src in sources:  # NUEVO
        name = src.get("name", "?")  # NUEVO
        stype = (src.get("type") or "").lower().strip()  # NUEVO
        url = (src.get("url") or "").strip()  # NUEVO
        category = (src.get("category") or "OTROS").strip().upper()  # NUEVO
        if stype != "rss":  # NUEVO
            print(f"[SKIP] {name}: type={stype!r} aún no soportado en este paso")  # NUEVO
            continue  # NUEVO
        if not url:  # NUEVO
            print(f"[WARN] {name}: sin URL")  # NUEVO
            continue  # NUEVO

        print(f"[INFO] Ingeriendo {name} (rss) → {url}")  # NUEVO
        try:  # NUEVO
            for raw in _fetch_rss_items_simple(url):  # NUEVO
                total_in += 1  # NUEVO
                item = dict(raw)  # NUEVO
                item["source"] = name  # mantener nombre canónico del sources.json  # NUEVO
                item["category"] = category  # NUEVO
                item["canonical_url"] = _canon(item["url"])  # NUEVO
                total_ok += _insert_article(item)  # NUEVO
        except Exception as e:  # NUEVO
            total_err += 1  # NUEVO
            print(f"[ERROR] Ingesta falló para {name}: {e}")  # NUEVO

    print(f"[INFO] Dynamic sources: in={total_in} inserted={total_ok} sources_failed={total_err}")  # NUEVO

SOURCES_PATH = Path(__file__).resolve().parents[1] / "data" / "sources.json"  # ajusta si tu estructura difiere
def ingest_from_dynamic_sources():
    """
    Lee data/sources.json y, para cada fuente habilitada type='rss':
      - Descarga y parsea el feed,
      - Enriquce cada item con source/category del sources.json,
      - Inserta en SQLite con INSERT OR IGNORE (dedupe por canonical_url).
    """
    # imports locales para no romper nada fuera
    import urllib.request
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime

    try:
        from core.utils import canonicalize_url as _canon
    except Exception:
        def _canon(u: str) -> str:
            return u

    from core.db import get_conn
    def _fetch_rss_items_simple(url: str):
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = resp.read()
        root = ET.fromstring(data)
        channel = root.find("./channel") or root
        for item in channel.findall("./item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate")
                   or item.findtext("{http://purl.org/dc/elements/1.1/}date")
                   or "").strip()
            try:
                dt = parsedate_to_datetime(pub) if pub else None
                iso = dt.isoformat() if dt else None
            except Exception:
                iso = None
            if title and link:
                yield {"title": title, "url": link, "date": iso}

    sources = load_sources()
    if not sources:
        print("[INFO] No hay fuentes dinámicas habilitadas en data/sources.json")
        return

    total_in = total_ok = total_err = 0
    for src in sources:
        name = (src.get("name") or "?").strip()
        stype = (src.get("type") or "").lower().strip()
        url = (src.get("url") or "").strip()
c       ategory = (SRC_MAP.get(name.lower(), (src.get("category") or "OTROS"))).strip().upper()  # NUEVO


        if stype != "rss":
            print(f"[SKIP] {name}: type={stype!r} aún no soportado en este paso")
            continue
        if not url:
            print(f"[WARN] {name}: sin URL")
            continue

        print(f"[INFO] Ingeriendo {name} (rss) → {url}")
        try:
            with get_conn() as conn:
                for raw in _fetch_rss_items_simple(url):
                    total_in += 1
                    title = (raw.get("title") or "").strip()
                    link = (raw.get("url") or "").strip()
                    can = _canon(link)
                    date = raw.get("date") or ""
                    if not (title and link and can):
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO articles (title, url, canonical_url, date, source, category) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (title, link, can, date, name, category),
                    )
                    total_ok += 1
        except Exception as e:
            total_err += 1
            print(f"[ERROR] Ingesta falló para {name}: {e}")

    print(f"[INFO] Dynamic sources: in={total_in} inserted={total_ok} sources_failed={total_err}")    
def load_sources() -> list[dict]:
    """
    Carga el registro dinámico de fuentes desde data/sources.json.
    Devuelve una lista de dicts con claves: name, type, url, category, enabled, interval_minutes.
    Si el archivo no existe o está mal, devuelve lista vacía (y loguea).
    """
    try:
        if not SOURCES_PATH.exists():
            return []
        data = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
        items = data.get("sources", [])
        out = []
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
        # Usa tu logger si lo tienes
        print(f"[WARN] load_sources() failed: {e}")
        return []
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


