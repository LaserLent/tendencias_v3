# tests/test_pagination.py
from fastapi.testclient import TestClient
from api.app import app

client = TestClient(app)

def test_items_pagination_headers_and_limits():
    # Primer window
    r1 = client.get("/items?limit=3&offset=0")
    assert r1.status_code == 200
    assert "X-Total-Count" in r1.headers
    total = int(r1.headers["X-Total-Count"])
    data1 = r1.json()
    assert isinstance(data1, list)
    assert 0 < len(data1) <= 3  # respeta limit

    # Segundo window (desplazado), debe dar 200 con distinto ETag
    r2 = client.get("/items?limit=3&offset=3")
    assert r2.status_code == 200
    data2 = r2.json()
    assert isinstance(data2, list)
    assert 0 <= len(data2) <= 3

    # ETag distinto entre ventanas
    etag1 = r1.headers.get("ETag")
    etag2 = r2.headers.get("ETag")
    assert etag1 and etag2 and etag1 != etag2
