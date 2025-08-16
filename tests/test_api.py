# tests/test_api.py
from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)

def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data and data["status"] == "ok"
    assert "items_total" in data

def test_items_ok_and_etag():
    r = client.get("/items?limit=5")
    assert r.status_code in (200, 304)
    # Si es 200, debe venir JSON con lista y ETag
    if r.status_code == 200:
        assert isinstance(r.json(), list)
        assert "ETag" in r.headers
    # Si es 304, es porque el ETag coincidió (lo cual también es correcto)

def test_items_304_flow():
    r1 = client.get("/items?limit=3")
    if r1.status_code != 200:
        # Si ya vino 304 por caché previa, forzamos otro query para obtener 200
        r1 = client.get("/items?limit=4")
        assert r1.status_code == 200
    etag = r1.headers.get("ETag")
    assert etag
    # Repetimos con If-None-Match para forzar 304
    r2 = client.get("/items?limit=3", headers={"If-None-Match": etag})
    assert r2.status_code == 304
