from fastapi import FastAPI, Query
from pydantic import BaseModel, HttpUrl
from typing import List, Optional
from datetime import datetime
import json, pathlib

class NewsItem(BaseModel):
    title: str
    url: HttpUrl
    canonical_url: HttpUrl
    date: str  # mantenemos str si el JSON no es ISO puro; validación estricta vendrá luego
    source: str
    category: str | None = None

DATA_PATH = pathlib.Path(__file__).resolve().parents[1] / "data" / "output.json"
app = FastAPI(title="Tendencias API", version="0.1.0")

def _load_items() -> list[dict]:
    if DATA_PATH.exists():
        try:
            return json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []

@app.get("/items", response_model=List[NewsItem])
def list_items(
    categoria: Optional[str] = Query(default=None),
    desde: Optional[str] = Query(default=None, description="Fecha ISO, ej: 2025-08-01T00:00:00"),
    texto: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000)
):
    data = _load_items()

    if categoria:
        c = categoria.lower()
        data = [x for x in data if (x.get("category") or "").lower() == c]

    if desde:
        try:
            # Intento flexible: si viene "Z" lo convertimos a ISO con offset
            dt_desde = datetime.fromisoformat(desde.replace("Z", "+00:00"))
            def _parse_date(s: str) -> datetime | None:
                try:
                    return datetime.fromisoformat((s or "").replace("Z", "+00:00"))
                except Exception:
                    return None
            data = [x for x in data if (d := _parse_date(x.get("date"))) and d >= dt_desde]
        except Exception:
            # Fecha inválida: se ignora el filtro (no rompemos la API)
            pass

    if texto:
        t = texto.lower()
        data = [x for x in data if t in (x.get("title","").lower()) or t in (x.get("source","").lower())]

    return data[:limit]