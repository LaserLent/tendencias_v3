import os
from fastapi.testclient import TestClient
import importlib

def test_startup_calls_ingest_once(monkeypatch):
    # Forzar auto-ingesta en startup
    os.environ["AUTO_INGEST_ON_START"] = "1"

    # Espía: contar llamadas a ingest_now
    calls = {"n": 0}
    def fake_ingest_now():
        calls["n"] += 1
        return {"inserted": 0, "updated": 0}

    # Import diferido para aplicar parche antes de crear la app
    services_ingest = importlib.import_module("services.ingest")
    monkeypatch.setattr(services_ingest, "ingest_now", fake_ingest_now, raising=True)

    # (Re)importar la app para asegurar que toma el lifespan actual
    if "api.app" in list(importlib.sys.modules):
        importlib.reload(importlib.import_module("api.app"))
    from api.app import app

    # Arrancar y apagar la app dentro del contexto -> ejecuta lifespan
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200

    # Debe haberse llamado exactamente una vez en STARTUP
    assert calls["n"] == 1

    # Limpieza
    os.environ.pop("AUTO_INGEST_ON_START", None)
