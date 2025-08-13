from fastapi import FastAPI, Query
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json, pathlib

# Usamos utils del proyecto para canonicalizar
from core.utils import canonicalize_url

class NewsItem(BaseModel):
    title: str
    url: str
    canonical_url: str
    date: str
    source: str
    category: Optional[str] = None

DATA_PATH = pathlib.Path(__file__).resolve().parents[1] / "data" / "output.json"
app = FastAPI(title="Tendencias API", version="0.1.2")

def _load_items() -> list[dict]:
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

def _get(d: dict, *keys: str) -> str:
    for k in keys:
        v = d.get(k)
        if v is not None:
            s = str(v).strip()
            if s:
                return s
    return ""

def _safe_normalize(x: dict) -> dict | None:
    if not isinstance(x, dict):
        return None
    # Acepta tanto claves EN como ES
    title = _get(x, "title", "titulo")
    url = _get(x, "url", "link")
    date = _get(x, "date", "fecha")
    source = _get(x, "source", "fuente")
    category = x.get("category") or x.get("categoria")
    can = _get(x, "canonical_url")
    if not can and url:
        try:
            can = canonicalize_url(url)
        except Exception:
            can = url

    # Requisitos mínimos
    if not (title and url and can and date and source):
        return None

    return {
        "title": title,
        "url": url,
        "canonical_url": can,
        "date": date,
        "source": source,
        "category": category if (category is None or isinstance(category, str)) else str(category),
    }

@app.get("/items", response_model=List[NewsItem])
def list_items(
    categoria: Optional[str] = Query(default=None),
    desde: Optional[str] = Query(default=None, description="Fecha ISO, ej: 2025-08-01T00:00:00"),
    texto: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000)
):
    raw = _load_items()
    data: list[dict] = []
    for x in raw:
        nx = _safe_normalize(x)
        if nx:
            data.append(nx)

    if categoria:
        c = categoria.lower()
        data = [x for x in data if (x.get("category") or "").lower() == c]

    if desde:
        try:
            dt_desde = datetime.fromisoformat(desde.replace("Z", "+00:00"))
            def _parse_date(s: str):
                try:
                    return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
                except Exception:
                    return None
            data = [x for x in data if (d := _parse_date(x.get("date"))) and d >= dt_desde]
        except Exception:
            pass

    if texto:
        t = texto.lower()
        data = [x for x in data if t in (x.get("title","").lower()) or t in (x.get("source","").lower())]

    safe: list[NewsItem] = []
    for x in data:
        try:
            safe.append(NewsItem(**x))
        except Exception:
            continue

    return safe[:limit]