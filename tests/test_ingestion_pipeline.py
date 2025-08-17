# tests/test_ingestion_pipeline.py
import json, importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

def _clear_articles(conn):
    cur = conn.cursor()
    cur.execute("DELETE FROM articles")
    conn.commit()

def _write_sources(tmp_path, name="TestFeed", url="https://example.com/feed"):
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({
        "sources": [{
            "name": name,
            "type": "rss",
            "url": url,
            "category": "OTROS",
            "enabled": True,
            "interval_minutes": 30
        }]
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

@pytest.fixture(autouse=True)
def clean_db():
    # Vacía la tabla 'articles' antes de cada test
    from core.db import init_db, get_conn
    init_db()
    with get_conn() as conn:
        _clear_articles(conn)
    yield
    with get_conn() as conn:
        _clear_articles(conn)

def test_ingest_dynamic_and_dedupe(tmp_path, monkeypatch):
    # Preparar SOURCES_PATH apuntando al tmp
    ingest = importlib.import_module("services.ingest")
    sources_path = _write_sources(tmp_path)
    monkeypatch.setattr(ingest, "SOURCES_PATH", sources_path, raising=True)

    # Fake RSS items (1 bueno, 1 duplicado por canónica, 1 antiguo, 1 sin fecha)
    now = datetime.now(timezone.utc)
    older = now - timedelta(days=60)

    def fake_fetch(_url: str):
        return iter([
            {"title": "Alpha", "url": "https://news.example.com/a?id=1", "date": now.isoformat()},
            {"title": "Alpha dup", "url": "https://news.example.com/a?id=1&utm_source=x", "date": now.isoformat()},
            {"title": "Old", "url": "https://news.example.com/old?id=2", "date": older.isoformat()},
            {"title": "NoDate", "url": "https://news.example.com/nodate", "date": ""},
        ])
    monkeypatch.setattr(ingest, "_fetch_rss_items_simple", fake_fetch, raising=True)

    # Ingesta
    from core.db import get_conn
    stats = ingest.ingest_from_dynamic_sources()
    assert stats["inserted"] >= 2           # Alpha + Old
    assert stats["updated"] >= 1            # dup actualiza
    assert stats["skipped"] >= 1            # NoDate
    assert stats["failed"] == 0

    # Comprobar en BD: unicidad por canonical_url y source_type/category razonables
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM articles")
        total = cur.fetchone()[0]
        assert total >= 2

        cur.execute("SELECT COUNT(*), COUNT(DISTINCT canonical_url) FROM articles")
        c_all, c_unique = cur.fetchone()
        assert c_all == c_unique            # no hay duplicados por canónica

        # source_type = 'rss'
        cur.execute("SELECT DISTINCT source_type FROM articles")
        stypes = {r[0] for r in cur.fetchall()}
        assert "rss" in stypes

def test_api_freshness_and_filters_and_etag(tmp_path, monkeypatch):
    # Preparar SOURCES_PATH y fake feed inicial
    ingest = importlib.import_module("services.ingest")
    sources_path = _write_sources(tmp_path)
    monkeypatch.setattr(ingest, "SOURCES_PATH", sources_path, raising=True)

    base = datetime.now(timezone.utc).replace(microsecond=0)
    first = base - timedelta(minutes=2)
    second = base - timedelta(minutes=1)

    def fake_fetch_round1(_url: str):
        return iter([
            {"title": "First", "url": "https://n.example.com/1", "date": first.isoformat()},
            {"title": "Second", "url": "https://n.example.com/2", "date": second.isoformat()},
        ])
    monkeypatch.setattr(ingest, "_fetch_rss_items_simple", fake_fetch_round1, raising=True)

    # 1) Ingesta inicial
    ingest.ingest_from_dynamic_sources()

    # 2) API: /items con 'desde' = base - 3 min => debe incluir First y Second ordenados por fecha desc
    from api.app import app
    client = TestClient(app)

    r = client.get("/items", params={"desde": (base - timedelta(minutes=3)).isoformat()})
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= 2
    # orden por fecha descendente (Second >= First)
    dates = [x["date"] for x in data]
    assert dates == sorted(dates, reverse=True)

    etag1 = r.headers.get("ETag")
    assert etag1

    # 3) Re-ingesta con un item nuevo más reciente -> ETag debe cambiar y la lista reflejarlo
    newest = base + timedelta(minutes=1)

    def fake_fetch_round2(_url: str):
        return iter([
            {"title": "First", "url": "https://n.example.com/1", "date": first.isoformat()},
            {"title": "Second", "url": "https://n.example.com/2", "date": second.isoformat()},
            {"title": "Newest", "url": "https://n.example.com/3", "date": newest.isoformat()},
        ])
    monkeypatch.setattr(ingest, "_fetch_rss_items_simple", fake_fetch_round2, raising=True)
    ingest.ingest_from_dynamic_sources()

    r2 = client.get("/items", params={"desde": (base - timedelta(minutes=3)).isoformat()},
                    headers={"If-None-Match": etag1})
    assert r2.status_code == 200  # debe invalidar 304 porque hay item nuevo
    data2 = r2.json()
    assert any(x["title"] == "Newest" for x in data2)
    etag2 = r2.headers.get("ETag")
    assert etag2 and etag2 != etag1

def test_category_fallback_map(tmp_path, monkeypatch):
    # Forzamos nombre que existe en SRC_MAP para priorizar categoría
    ingest = importlib.import_module("services.ingest")
    sources_path = _write_sources(tmp_path, name="Xataka")
    monkeypatch.setattr(ingest, "SOURCES_PATH", sources_path, raising=True)

    now = datetime.now(timezone.utc)
    def fake_fetch(_url: str):
        return iter([
            {"title": "CatMap", "url": "https://n.example.com/x", "date": now.isoformat()},
        ])
    monkeypatch.setattr(ingest, "_fetch_rss_items_simple", fake_fetch, raising=True)

    # Ingesta
    from core.db import get_conn
    ingest.ingest_from_dynamic_sources()

    # La categoría debe venir de SRC_MAP (prioritaria)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT category FROM articles WHERE source = 'Xataka' ORDER BY date DESC LIMIT 1")
        row = cur.fetchone()
        assert row and row[0] and row[0].upper().startswith("TECNO")
