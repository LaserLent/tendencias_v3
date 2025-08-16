# api/app.py
from fastapi import FastAPI, Query, Request, HTTPException
from typing import Optional
from datetime import datetime
import hashlib, os, logging

from api.helpers import (
    DATA_PATH,
    json_ok as _json,
    not_modified as _not_modified,
    load_items as _load_items,
    query as _query,
)

# DB opcional (helpers ya hace fallback a JSON)
try:
    from core.db import get_stats
    HAS_DB = True
except Exception:
    HAS_DB = False

# App y logging
app = FastAPI(title="Tendencias API", version="0.1.7")
logger = logging.getLogger("tendencias.api.app")
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_h)
logger.setLevel(logging.INFO)
logger.propagate = False

# Seguridad básica
@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp

# Auto-ingesta opcional al arrancar
@app.on_event("startup")
def _auto_ingest_on_start():
    if os.getenv("AUTO_INGEST_ON_START", "0") == "1":
        try:
            from services.ingest import ingest_now
            stats = ingest_now()
            logger.info("AUTO_INGEST_ON_START OK %s", stats)
        except Exception:
            logger.exception("AUTO_INGEST_ON_START FAILED")

@app.get("/health")
def health():
    # 1) BD primero
    if HAS_DB:
        try:
            s = get_stats()
            logger.info(
                "HEALTH_SOURCE=DB items_total=%s last_updated=%s",
                s.get("items_total", 0),
                s.get("last_updated")
            )
            return _json({
                "status": "ok",
                "items_total": s.get("items_total", 0),
                "last_updated": s.get("last_updated"),
            })
        except Exception:
            logger.exception("HEALTH_DB_FAILED")

    # 2) Fallback JSON
    items = _load_items()
    items_total = len(items)
    try:
        last_updated = datetime.fromtimestamp(DATA_PATH.stat().st_mtime).isoformat()
    except Exception:
        last_updated = None
    logger.info("HEALTH_SOURCE=JSON items_total=%d last_updated=%s", items_total, last_updated)
    return _json({"status": "ok", "items_total": items_total, "last_updated": last_updated})

@app.get("/items")
def list_items(
    request: Request,
    categoria: Optional[str] = Query(default=None),
    # ⬇️ Tipamos como datetime para validar formato automáticamente (422 si no es ISO válido)
    desde: Optional[datetime] = Query(default=None, description="Fecha ISO, ej: 2025-08-01T00:00:00+02:00"),
    hasta: Optional[datetime] = Query(default=None, description="Fecha ISO inclusive, ej: 2025-08-07T23:59:59+02:00"),
    fuente: Optional[str] = Query(default=None, description="Filtro exacto por fuente, ej: 'Xataka' o 'Reddit r/technology'"),
    texto: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    # Normalizamos a ISO para _query/DB (o None si no viene)
    ds = desde.isoformat() if desde else None
    hs = hasta.isoformat() if hasta else None

    try:
        # 1) total real sin paginación
        data_all = _query(
            categoria=categoria,
            desde=ds,
            hasta=hs,
            texto=texto,
            fuente=fuente,
            limit=10**9,   # “sin límite” práctico
            offset=0,
        )
        total = len(data_all)

        # 2) ventana paginada
        window = data_all[offset: offset + limit]
        out = [{
            "title": x.get("title") or "",
            "url": x.get("url") or "",
            "canonical_url": x.get("canonical_url") or "",
            "date": x.get("date") or "",
            "source": x.get("source") or "",
            "category": x.get("category"),
        } for x in window]

        # 3) ETag estable (incluye filtros normalizados y borde temporal de la ventana)
        first_date = (window[0].get("date") if window else "") or ""
        last_date  = (window[-1].get("date") if window else "") or ""
        etag_raw = "|".join([
            str(total), str(limit), str(offset),
            categoria or "", ds or "", hs or "",
            texto or "", fuente or "",
            first_date, last_date
        ])
        etag = hashlib.md5(etag_raw.encode("utf-8")).hexdigest()

        inm = request.headers.get("If-None-Match")
        if inm and inm == etag:
            return _not_modified(etag)

        resp = _json(out)
        resp.headers["X-Total-Count"] = str(total)
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "public, max-age=60"
        return resp
    except Exception:
        logger.exception("ITEMS_500")
        raise HTTPException(status_code=500, detail="Internal server error")
