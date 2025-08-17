# --- IMPORTS que usan las utilidades ---
import os
from pathlib import Path
from datetime import datetime, timedelta 
from fastapi.responses import JSONResponse, Response
from typing import Optional, List, Dict
import json, html
import logging
from core.text_clean import clean_text

logger = logging.getLogger("tendencias.api.helpers")
# Emitir logs aunque Uvicorn no configure este logger
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)
logger.propagate = False

# --- Canonicalización de URLs ---
try:
    from core.utils import canonicalize_url as _canon
except Exception:
    def _canon(u: str) -> str:
        return u

# --- DB opcional para helpers ---
try:
    from core.db import get_articles  # type: ignore
    HAS_DB = True
except Exception:
    HAS_DB = False

# --- CONSTANTES Y RUTAS ---
DATA_PATH = Path(
    os.getenv("TRENDS_DATA_PATH", str(Path(__file__).resolve().parents[1] / "data" / "output.json"))
)
JSON_MEDIA = "application/json; charset=utf-8"

# NUEVO: normaliza 'hasta' para que 'YYYY-MM-DD' se convierta en el día siguiente (exclusivo)
def _normalize_until(hasta: Optional[str]) -> Optional[str]:
    if not hasta:
        return None
    if len(hasta) == 10 and hasta[4] == '-' and hasta[7] == '-':
        d = datetime.strptime(hasta, "%Y-%m-%d").date()
        return (d + timedelta(days=1)).isoformat()
    return hasta

def _parse_iso_safe(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # soporta 'YYYY-MM-DD' y 'YYYY-MM-DDTHH:MM:SS' (sin Z)
        return datetime.fromisoformat(s.replace("Z",""))
    except Exception:
        return None

def _json(payload: dict | list, status: int = 200) -> JSONResponse:
    return JSONResponse(content=payload, media_type=JSON_MEDIA, status_code=status)

def _not_modified(etag: str) -> Response:
    resp = Response(status_code=304)
    resp.headers["ETag"] = etag
    resp.headers["Cache-Control"] = "public, max-age=60"
    return resp

def _load_items() -> list:
    if not DATA_PATH.exists():
        return []
    try:
        txt = DATA_PATH.read_text(encoding="utf-8")
        data = json.loads(txt)
        if isinstance(data, dict) and "value" in data and isinstance(data["value"], list):
            return data["value"]
        if isinstance(data, list):
            return data
        return []
    except Exception:
        logger.exception("LOAD_ERROR reading %s", DATA_PATH)
        return []
        

def _get(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return ""
    
def _safe_normalize(x: dict) -> Optional[dict]:
    if not isinstance(x, dict):
        return None

    title = clean_text(_get(x, "title", "titulo"))
    url = html.unescape(_get(x, "url", "link"))
    if url.startswith("/r/"):
        url = "https://www.reddit.com" + url
    date = _get(x, "date", "fecha")
    source = clean_text(_get(x, "source", "fuente"))
    category = clean_text(x.get("category") or x.get("categoria")) or None
    can = _get(x, "canonical_url") or (_canon(url) if url else "")

    if not (title and url and can and date and source):
        return None

    return {
        "title": title,
        "url": url,
        "canonical_url": can,
        "date": date,
        "source": source,
        "category": category,
    }
def _ts(s: Optional[str]) -> float:
    try:
        return datetime.fromisoformat((s or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0

def _query(
    categoria: Optional[str],
    desde: Optional[str],
    hasta: Optional[str],          
    texto: Optional[str],
    fuente: Optional[str],         
    limit: int,
    offset: int,
    tipo: Optional[str] = None
) -> list:
    data: list = []
    source = "UNKNOWN"
    until = _normalize_until(hasta)   # NUEVO
    # 1) Intento DB primero (pedimos amplio y filtramos extra en Python)
    if HAS_DB:
        try:
            rows = get_articles(
                category=categoria,
                text=texto,
                since=desde,
                until=until,               # NUEVO
                source=fuente,             # NUEVO
                limit=limit,               # NUEVO (paginación real en SQL)
                type=tipo,  
                offset=offset,             # NUEVO
            )
            data = [{
                "title": r["title"],
                "url": r["url"],
                "canonical_url": r["canonical_url"],
                "date": r["date"],
                "source": r["source"],
                "category": r["category"],
            } for r in rows]
            source = "DB"
        except Exception:
            logger.exception(
                "DB_QUERY_ERROR category=%r text=%r since=%r limit=%s offset=%s",
                categoria, texto, desde, limit, offset
            )
            # caemos a JSON

    # 2) Fallback JSON si no hay DB o falló
    if not data and source != "DB":
        raw = _load_items()
        data = [y for y in (_safe_normalize(i) for i in raw) if y]
        source = "JSON"

    # 3) Filtros SOLO para fallback JSON (en DB ya se aplicaron)
    if source != "DB":                          # NUEVO
        # fecha inferior (desde)
        if desde:
            dt_desde = _ts(desde)
            if dt_desde:
                data = [x for x in data if _ts(x.get("date")) >= dt_desde]

        # fecha superior (hasta)  ← recuerda: aquí 'hasta' NO está normalizado
        if hasta:
            dt_hasta = _ts(hasta)
            if dt_hasta:
                data = [x for x in data if _ts(x.get("date")) <= dt_hasta]

        # categoria
        if categoria:
            c = categoria.strip().lower()
            data = [x for x in data if (x.get("category") or "").lower() == c]

        # fuente (case-insensitive exacto)
        if fuente:
            f = fuente.strip().lower()
            data = [x for x in data if (x.get("source") or "").strip().lower() == f]

        # texto (título + fuente)
        if texto:
            t = (texto or "").strip().lower()
            if t:
                data = [x for x in data if t in (x.get("title","") + " " + (x.get("source") or "")).lower()]


    # 4) Orden fecha desc + canonical_url como desempate
    data.sort(
        key=lambda x: (_ts(x.get("date")), (x.get("canonical_url") or x.get("url") or "")),
        reverse=True
    )

    logger.info("QUERY_SOURCE=%s items=%d", source, len(data))
    return data


from core.text_clean import clean_text
# --- ALIAS PÚBLICOS ESPERADOS POR app.py ---
# Para no reescribir cuerpos ni referencias internas,
# exponemos nombres "públicos" que importará app.py.
try:
    json_ok = _json              # _json -> json_ok
except NameError:
    pass
try:
    not_modified = _not_modified # _not_modified -> not_modified
except NameError:
    pass
try:
    load_items = _load_items     # _load_items -> load_items
except NameError:
    pass
try:
    normalize = _safe_normalize  # _safe_normalize -> normalize
except NameError:
    pass
try:
    ts = _ts                     # _ts -> ts
except NameError:
    pass
try:
    query = _query               # _query -> query
except NameError:
    pass

__all__ = [
    "DATA_PATH",
    "json_ok",
    "not_modified",
    "load_items",
    "query",
    # opcionales por si los importas en el futuro:
    "normalize",
    "ts",
]
