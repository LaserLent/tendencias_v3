from fastapi.testclient import TestClient
from api.app import app

def test_validation_errors_and_limits():
    c = TestClient(app)
    # fecha inválida => 422
    r = c.get("/items", params={"desde": "no-es-fecha"})
    assert r.status_code == 422
    # limit > 1000 => 422
    r = c.get("/items", params={"limit": 1001})
    assert r.status_code == 422
    # offset negativo => 422
    r = c.get("/items", params={"offset": -1})
    assert r.status_code == 422

def test_security_headers_present():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "no-referrer"
