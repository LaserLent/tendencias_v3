from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Iterable, Optional, Dict, Any

DB_PATH = Path("data/app.db")
DATA_DIR = DB_PATH.parent

def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Abre una conexión SQLite con PRAGMAs seguros y razonables.
    - WAL para concurrencia (lecturas no bloquean escrituras).
    - foreign_keys ON.
    - synchronous NORMAL (equilibrio durabilidad/rendimiento).
    """
    _ensure_dirs()
    path = str((db_path or DB_PATH).resolve())
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    with conn:  # PRAGMAs en cada apertura
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """
    Crea el esquema inicial si no existe. Idempotente.
    Tablas:
      - taxonomy(id, name, parent_id)
      - sources(id, name, kind, url, enabled)
      - articles(id, title, url, canonical_url, date, source, category, created_at)
    Índices:
      - UNIQUE(canonical_url) para dedupe simple y robusto.
      - idx por fecha y categoría para filtros de API.
    """
    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS taxonomy (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              parent_id INTEGER REFERENCES taxonomy(id) ON DELETE SET NULL
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              kind TEXT NOT NULL,          -- rss | reddit | youtube | other
              url  TEXT NOT NULL,
              enabled INTEGER NOT NULL DEFAULT 1
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              title TEXT NOT NULL,
              url   TEXT NOT NULL,
              canonical_url TEXT NOT NULL,
              date  TEXT,                   -- ISO8601
              source TEXT,                  -- Reddit r/..., MIT Tech Review, ...
              category TEXT,                -- CIENCIA / TECNOLOGIA / CULTURA / OTROS / ...
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """)
            # Dedupe por URL canónica (simple y eficaz)
            conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS ux_articles_canonical
            ON articles(canonical_url);
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_articles_date ON articles(date);")
            conn.execute("CREATE INDEX IF NOT EXISTS ix_articles_category ON articles(category);")
    finally:
        if close_later:
            conn.close()

def upsert_article(rec: Dict[str, Any], conn: Optional[sqlite3.Connection] = None) -> bool:
    """
    Inserta o actualiza un artículo por canonical_url (UNIQUE).
    Devuelve True si insertó; False si actualizó.
    Campos esperados en rec (esquema API canónico):
      title, url, canonical_url, date, source, category
    """
    required = ("title","url","canonical_url")
    if any(not rec.get(k) for k in required):
        return False

    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        with conn:
            cur = conn.execute("""
              INSERT INTO articles (title, url, canonical_url, date, source, category)
              VALUES (:title, :url, :canonical_url, :date, :source, :category)
              ON CONFLICT(canonical_url) DO UPDATE SET
                title=excluded.title,
                url=excluded.url,
                date=excluded.date,
                source=excluded.source,
                category=excluded.category
            """, {
                "title": rec.get("title"),
                "url": rec.get("url"),
                "canonical_url": rec.get("canonical_url"),
                "date": rec.get("date"),
                "source": rec.get("source"),
                "category": rec.get("category"),
            })
            # rowcount = 1 en INSERT y en UPDATE, pero podemos detectar por existencia previa
            return cur.lastrowid is not None
    finally:
        if close_later:
            conn.close()

def get_articles(
    *,
    category: Optional[str]=None,
    text: Optional[str]=None,
    since: Optional[str]=None,     # ISO8601 (inclusive)
    limit: int=50,
    conn: Optional[sqlite3.Connection]=None
) -> Iterable[sqlite3.Row]:
    """
    Devuelve artículos con filtros básicos para la API.
    - since: filtro mínimo por fecha ISO.
    - text: LIKE en title (case-insensitive).
    """
    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        where = []
        params: Dict[str, Any] = {}
        if category:
            where.append("category = :category")
            params["category"] = category
        if since:
            where.append("date >= :since")
            params["since"] = since
        if text:
            where.append("LOWER(title) LIKE :text")
            params["text"] = f"%{text.lower()}%"

        sql = "SELECT id, title, url, canonical_url, date, source, category FROM articles"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY date DESC NULLS LAST, id DESC LIMIT :limit"

        params["limit"] = int(max(1, min(limit, 500)))
        cur = conn.execute(sql, params)
        return cur.fetchall()
    finally:
        if close_later:
            conn.close()

def get_stats(conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
    """
    Devuelve métricas rápidas: total y última fecha.
    """
    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        last  = conn.execute("SELECT MAX(date) FROM articles").fetchone()[0]
        return {"items_total": int(total), "last_updated": last}
    finally:
        if close_later:
            conn.close()