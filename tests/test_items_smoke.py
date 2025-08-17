# tests/test_items_smoke.py
# Smoke tests de la API /items: estado, cabeceras, paginación, rango, fuente y ETag.
# No modifica la BD. Se adapta tanto a origen DB como JSON.

from datetime import datetime, timedelta
from fastapi.testclient import TestClient
import re

# Importa la app ASGI
from api.app import app  # noqa: E402

client = TestClient(app)

def _iso_to_date(s: str) -> datetime.date:
    # Soporta 'YYYY-MM-DD' y 'YYYY-MM-DDTHH:MM:SS(+TZ)'
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()

def test_items_basic_ok():
    r = client.get("/items", params={"limit": 10, "offset": 0})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")
    assert "X-Total-Count" in r.headers
    assert re.fullmatch(r"\d+", r.headers["X-Total-Count"]) is not None
    assert "ETag" in r.headers
    data = r.json()
    assert isinstance(data, list)
    assert len(data) <= 10

def test_etag_304_not_modified():
    r1 = client.get("/items", params={"limit": 5, "offset": 0})
    assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    if not etag:
        # si no hay ETag, no tiene sentido continuar este test
        return
    r2 = client.get("/items", params={"limit": 5, "offset": 0}, headers={"If-None-Match": etag})
    assert r2.status_code == 304

def test_pagination_no_overlap():
    r1 = client.get("/items", params={"limit": 5, "offset": 0})
    r2 = client.get("/items", params={"limit": 5, "offset": 5})
    assert r1.status_code == 200 and r2.status_code == 200
    d1, d2 = r1.json(), r2.json()
    if len(d1) == 0 or len(d2) == 0:
        # dataset demasiado pequeño: nada que verificar
        return
    set1 = {x.get("canonical_url") or x.get("url") for x in d1}
    set2 = {x.get("canonical_url") or x.get("url") for x in d2}
    assert set1.isdisjoint(set2)

def test_range_inclusive_days_exclusive_sql():
    # Tomamos una fecha real del dataset y pedimos solo ese día
    r0 = client.get("/items", params={"limit": 1, "offset": 0})
    assert r0.status_code == 200
    data0 = r0.json()
    if not data0:
        return  # no hay datos
    day = _iso_to_date(data0[0]["date"])
    desde = day.isoformat()
    hasta = day.isoformat()  # la API normaliza a lim. exclusivo del día siguiente
    r = client.get("/items", params={"desde": desde, "hasta": hasta, "limit": 50})
    assert r.status_code == 200
    data = r.json()
    # Todos deben caer en ese mismo día (según normalización)
    for x in data:
        assert _iso_to_date(x["date"]) == day

def test_source_filter_uses_exact_match():
    # Detecta una fuente existente y verifica que el filtro funciona
    r0 = client.get("/items", params={"limit": 20, "offset": 0})
    assert r0.status_code == 200
    data0 = r0.json()
    if not data0:
        return
    source = next((x["source"] for x in data0 if x.get("source")), None)
    if not source:
        return
    r = client.get("/items", params={"fuente": source, "limit": 10})
    assert r.status_code == 200
    data = r.json()
    # Si no hay coincidencias, el total será 0: caso válido
    total = int(r.headers.get("X-Total-Count", "0"))
    if total == 0:
        return
    # Si hay, todas deben tener exactamente esa fuente (NOCASE ya lo maneja el SQL)
    for x in data:
        assert (x.get("source") or "") == source

def test_total_header_consistency():
    # El total debe ser >= elementos de la página y estable con distintos offsets
    r1 = client.get("/items", params={"limit": 7, "offset": 0})
    r2 = client.get("/items", params={"limit": 7, "offset": 7})
    assert r1.status_code == 200 and r2.status_code == 200
    t1 = int(r1.headers.get("X-Total-Count", "0"))
    t2 = int(r2.headers.get("X-Total-Count", "0"))
    assert t1 == t2  # mismo total con distinto offset
    assert t1 >= len(r1.json())

def test_health_endpoint_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/json")
    data = r.json()
    assert isinstance(data, dict)

    # status presente y saludable (case-insensitive)
    status = str(data.get("status", "")).lower()
    assert status in {"ok", "healthy", "up", "ready"}

    # Campos opcionales (si existen)
    if "items_total" in data:
        assert isinstance(data["items_total"], int)
        assert data["items_total"] >= 0

    if "last_updated" in data and data["last_updated"]:
        # Acepta 'YYYY-MM-DD' o ISO con hora/TZ
        from datetime import datetime
        try:
            datetime.fromisoformat(str(data["last_updated"]).replace("Z", "+00:00"))
        except Exception:
            assert False, "last_updated no es ISO-8601 válido"
