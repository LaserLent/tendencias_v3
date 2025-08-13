from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import json, pathlib, html

# Canonicalización y limpieza
try:
    from core.utils import canonicalize_url as _canon
except Exception:
    def _canon(u: str) -> str:
        return u
from core.text_clean import clean_text

class NewsItem(BaseModel):
    title: str
    url: str
    canonical_url: str
    date: str
    source: str
    category: Optional[str] = None

DATA_PATH = pathlib.Path(__file__).resolve().parents[1] / "data" / "output.json"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Hook de arranque: lista rutas registradas (útil para debug/ops)
    print("ROUTES(boot):", [r.path for r in app.routes])
    yield

app = FastAPI(title="Tendencias API", version="0.1.6", lifespan=lifespan)

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
    except Exception as e:
        print("LOAD_ERROR:", repr(e))
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
    url   = html.unescape(_get(x, "url", "link"))
    date  = _get(x, "date", "fecha")
    source= clean_text(_get(x, "source", "fuente"))
    category_raw = x.get("category") or x.get("categoria")
    category = clean_text(category_raw) or None

    # Repara URLs relativas de Reddit
    if url and not url.startswith("http"):
        if url.startswith("/r/"):
            url = "https://www.reddit.com" + url

    can = _get(x, "canonical_url")
    if not can and url:
        try:
            can = _canon(url)
        except Exception:
            can = url

    if not (title, url, can, date, source):
        return None

    return {
        "title": title,
        "url": url,
        "canonical_url": can,
        "date": date,
        "source": source,
        "category": category,
    }

@app.get("/health")
def health():
    raw = _load_items()
    norm = [y for y in (_safe_normalize(i) for i in raw) if y]
    try:
        mtime = DATA_PATH.stat().st_mtime
        last_updated = datetime.fromtimestamp(mtime).isoformat()
    except Exception:
        last_updated = None
    return JSONResponse(
        content={"status": "ok", "items_total": len(norm), "last_updated": last_updated},
        media_type="application/json; charset=utf-8",
    )

@app.get("/items")
def list_items(
    categoria: Optional[str] = Query(default=None),
    desde: Optional[str] = Query(default=None, description="Fecha ISO, ej: 2025-08-01T00:00:00"),
    texto: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000)
):
    try:
        raw = _load_items()
        data = [y for y in (_safe_normalize(i) for i in raw) if y]

        if categoria:
            c = categoria.lower()
            data = [x for x in data if (x.get("category") or "").lower() == c]

        if desde:
            try:
                dt_desde = datetime.fromisoformat(desde.replace("Z", "+00:00"))
                def _pd(s: str):
                    try:
                        return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
                    except Exception:
                        return None
                data = [x for x in data if (d := _pd(x.get("date"))) and d >= dt_desde]
            except Exception:
                pass

        if texto:
            t = texto.lower()
            data = [x for x in data if t in (x.get("title","").lower()) or t in (x.get("source","").lower())]

        try:
            out = [NewsItem(**x).model_dump() for x in data[:limit]]
        except Exception:
            out = data[:limit]

        return JSONResponse(content=out, media_type="application/json; charset=utf-8")
    except Exception as e:
        print("ITEMS_500:", repr(e))
        return JSONResponse(content=[], media_type="application/json; charset=utf-8")