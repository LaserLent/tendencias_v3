# tests/test_storage_and_classification.py
import json, importlib
from datetime import datetime, timezone, timedelta
import sqlite3
import pytest
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def clean_db():
    from core.db import init_db, get_conn
    init_db()
    with get_conn() as conn:
        conn.execute("DELETE FROM articles")
        conn.commit()
    yield
    with get_conn() as conn:
        conn.execute("DELETE FROM articles")
        conn.commit()

def _write_sources(tmp_path, name="Xataka", url="https://example.com/feed"):
    p = tmp_path / "sources.json"
    p.write_text(json.dumps({
        "sources": [{
            "name": name, "type": "rss", "url": url,
            "category": "OTROS", "enabled": True, "interval_minutes": 30
        }]
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return p

def test_db_schema_and_unique_index():
    from core.db import get_conn
    with get_conn() as conn:
        # columnas imprescindibles
        cols = {r[1] for r in conn.execute("PRAGMA table_info(articles)").fetchall()}
        assert {"title","url","canonical_url","date","source","category"} <= cols
        # índice/unique sobre canonical_url
        idx = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='articles'"
        )]
        # no exigimos nombre exacto, pero sí que exista algún índice único sobre canonical_url
        pragma_idx_list = conn.execute("PRAGMA index_list(articles)").fetchall()
        unique_idxs = [i for i in pragma_idx_list if i[2]]  # 2=unique flag
        ok_unique = False
        for (seq, name, unique, origin, partial) in unique_idxs:
            info = conn.execute(f"PRAGMA index_info({name})").fetchall()
            cols_in_idx = [c[2] for c in info]
            if cols_in_idx == ["canonical_url"]:
                ok_unique = True
                break
        assert ok_unique, "Falta UNIQUE(canonical_url)"

def test_dynamic_ingest_dedupe_and_category_map(tmp_path, monkeypatch):
    ingest = importlib.import_module("services.ingest")
    sources_path = _write_sources(tmp_path, name="Xataka")
    monkeypatch.setattr(ingest, "SOURCES_PATH", sources_path, raising=True)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    def fake_fetch(_):
        return iter([
            {"title":"A","url":"https://site/a?id=1","date": now.isoformat()},
            {"title":"A dup","url":"https://site/a?id=1&utm=foo","date": now.isoformat()},
        ])
    monkeypatch.setattr(ingest, "_fetch_rss_items_simple", fake_fetch, raising=True)

    stats = ingest.ingest_from_dynamic_sources()
    assert stats["inserted"] >= 1
    assert stats["updated"] >= 1  # el duplicado debe actualizar

    from core.db import get_conn
    with get_conn() as conn:
        # debe haber 1 fila por canónica
        cur = conn.execute("SELECT COUNT(*), COUNT(DISTINCT canonical_url) FROM articles")
        total, uniq = cur.fetchone()
        assert total == uniq == 1
        # categoría prioritaria por SRC_MAP ("Xataka" -> TECNOLOGIA*)
        cat = conn.execute("SELECT category FROM articles LIMIT 1").fetchone()[0]
        assert cat.upper().startswith("TECNO"), cat

def test_builtins_source_type_detection(monkeypatch):
    # Parchear fetchers para no depender de red
    import fetchers.reddit_fetcher as rf
    import fetchers.youtube_fetcher as yf
    import fetchers.rss_fetcher as rssf
    rf.obtener_de_reddit = lambda: [{
        "title":"Post ReddiT", "url":"https://reddit.com/r/tech/1",
        "date": datetime.now(timezone.utc).isoformat(),
        "source":"Reddit r/technology", "category":"OTROS"
    }]
    yf.obtener_de_youtube = lambda: [{
        "title":"Video YT","url":"https://youtu.be/abc",
        "date": datetime.now(timezone.utc).isoformat(),
        "source":"YouTube - Canal X","category":"OTROS"
    }]
    rssf.obtener_noticias_recientes = lambda: [{
        "title":"RSS Item","url":"https://blog.example.com/x",
        "date": datetime.now(timezone.utc).isoformat(),
        "source":"Blog X","category":"OTROS"
    }]

    ingest = importlib.import_module("services.ingest")
    stats = ingest.ingest_now()
    assert stats["inserted"] + stats["updated"] >= 3

    from core.db import get_conn
    with get_conn() as conn:
        stypes = {r[0] for r in conn.execute("SELECT DISTINCT source_type FROM articles")}
        assert {"subreddit","youtube","rss"} <= stypes

def test_api_filters_return_stored_items(tmp_path, monkeypatch):
    # fuentes dinámicas -> items recientes
    ingest = importlib.import_module("services.ingest")
    sources_path = _write_sources(tmp_path, name="TechCrunch")
    monkeypatch.setattr(ingest, "SOURCES_PATH", sources_path, raising=True)

    base = datetime.now(timezone.utc).replace(microsecond=0)
    items = [
        {"title":"New-1","url":"https://n/1","date": (base - timedelta(minutes=2)).isoformat()},
        {"title":"New-2","url":"https://n/2","date": (base - timedelta(minutes=1)).isoformat()},
    ]
    monkeypatch.setattr(ingest, "_fetch_rss_items_simple", lambda _: iter(items), raising=True)
    ingest.ingest_from_dynamic_sources()

    from api.app import app
    client = TestClient(app)

    # filtro por fecha desde => debe devolver los dos
    r = client.get("/items", params={"desde": (base - timedelta(minutes=3)).isoformat()})
    assert r.status_code == 200
    data = r.json()
    titles = {x["title"] for x in data}
    assert {"New-1","New-2"} <= titles
