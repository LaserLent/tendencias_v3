# tests/test_json_fallback.py
from fastapi.testclient import TestClient
from api.app import app
import api.helpers as helpers

client = TestClient(app)

def test_items_json_fallback_monkeypatch():
    # Fuerza fallback a JSON
    old = helpers.HAS_DB
    helpers.HAS_DB = False
    try:
        r = client.get("/items?limit=5")
        assert r.status_code in (200, 304)
        if r.status_code == 200:
            data = r.json()
            assert isinstance(data, list)
            # Si hay fichero JSON cargado, debería haber >=0 items (al menos valida tipo)
    finally:
        # Restaura el valor original para no afectar otros tests
        helpers.HAS_DB = old
