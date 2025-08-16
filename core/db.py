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
            CREATE UNIQUE INDEX IF NOT EXISTS ux_sources_url
            ON sources(url);
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
    Devuelve True si insertó; False si actualizó o ya existía.
    Campos esperados en rec (esquema API canónico):
      title, url, canonical_url, date, source, category
    """
    required = ("title", "url", "canonical_url")
    if any(not rec.get(k) for k in required):
        return False

    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        with conn:
            # 1) Comprobar existencia previa (criterio de dedupe)
            row = conn.execute(
                "SELECT 1 FROM articles WHERE canonical_url = ?",
                (rec.get("canonical_url"),)
            ).fetchone()
            existed = bool(row)

            # 2) UPSERT atómico (inserta o actualiza campos)
            conn.execute("""
                INSERT INTO articles (title, url, canonical_url, date, source, category)
                VALUES (:title, :url, :canonical_url, :date, :source, UPPER(:category))
                ON CONFLICT(canonical_url) DO UPDATE SET
                    title   = excluded.title,
                    url     = excluded.url,
                    source  = excluded.source,
                    -- conserva la fecha más reciente
                    date    = CASE
                                WHEN excluded.date IS NULL THEN articles.date
                                WHEN articles.date IS NULL THEN excluded.date
                                WHEN excluded.date > articles.date THEN excluded.date
                                ELSE articles.date
                              END,
                    -- no degradar a OTROS si ya teníamos algo mejor
                    category= CASE
                                WHEN excluded.category IS NULL OR excluded.category = 'OTROS'
                                     THEN articles.category
                                ELSE UPPER(excluded.category)
                              END
            """, {
                "title": rec.get("title"),
                "url": rec.get("url"),
                "canonical_url": rec.get("canonical_url"),
                "date": rec.get("date"),
                "source": rec.get("source"),
                "category": rec.get("category"),
            })
            # 3) Si no existía, fue INSERT; si existía, fue UPDATE
            return not existed
    finally:
        if close_later:
            conn.close()

def get_articles(
    *,
    category: Optional[str]=None,
    text: Optional[str]=None,
    since: Optional[str]=None,         # ISO8601 (inclusive)
    until: Optional[str]=None,         # NUEVO: límite EXCLUSIVO (normalizado en la API)
    source: Optional[str]=None,        # filtro por fuente (igualdad, no LIKE)
    offset: int=0,                     # paginación real en SQL
    limit: int=50,
    conn: Optional[sqlite3.Connection]=None
) -> Iterable[sqlite3.Row]:
    """
    Devuelve artículos con filtros básicos para la API.
    - since: filtro mínimo por fecha (ISO). Si la columna date es INTEGER, se convierte a epoch para comparar.
    - until: límite EXCLUSIVO. Si la columna date es INTEGER, se convierte a epoch para comparar.  # NUEVO
    - text: LIKE en title/source (case-insensitive).
    - source: igualdad case-insensitive.
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
            # NUEVO: compara manzana con manzana (INTEGER epoch vs TEXT ISO)
            where.append(
                "date >= CASE WHEN typeof(date)='integer' THEN strftime('%s', :since) ELSE :since END"
            )  # NUEVO
            params["since"] = since  # NUEVO

        if until:
            # NUEVO: límite EXCLUSIVO, con conversión a epoch si la columna es INTEGER
            where.append(
                "date < CASE WHEN typeof(date)='integer' THEN strftime('%s', :until) ELSE :until END"
            )  # NUEVO
            params["until"] = until  # NUEVO

        if text:
            where.append("(LOWER(title) LIKE :text OR LOWER(IFNULL(source,'')) LIKE :text)")
            params["text"] = f"%{text.lower()}%"

        if source is not None:
            where.append("source = :source COLLATE NOCASE")  # NUEVO
            params["source"] = source                         # NUEVO

        sql = "SELECT id, title, url, canonical_url, date, source, category FROM articles"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY (date IS NULL) ASC, date DESC, id DESC "
        sql += "LIMIT :limit OFFSET :offset"

        params["offset"] = int(max(0, offset))
        params["limit"]  = int(max(1, min(limit, 500)))

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
            # ---------------------------
# Configuración: sources y taxonomy
# ---------------------------

from typing import List

def add_source(name: str, url: str, kind: str = "rss", enabled: bool = True,
               conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Inserta una fuente si no existe (por URL). Devuelve su id.
    Esquema actual: sources(id, name, kind, url, enabled)
    """
    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        with conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO sources(name, kind, url, enabled) VALUES (?, ?, ?, ?)",
                (name, kind, url, 1 if enabled else 0),
            )
            if cur.lastrowid:
                return int(cur.lastrowid)
            row = conn.execute("SELECT id FROM sources WHERE url = ?", (url,)).fetchone()
            return int(row["id"]) if row else 0
    finally:
        if close_later:
            conn.close()

def get_sources(only_enabled: bool = True,
                conn: Optional[sqlite3.Connection] = None) -> List[sqlite3.Row]:
    """
    Devuelve lista de fuentes para los fetchers / importadores.
    """
    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        where = "WHERE enabled = 1" if only_enabled else ""
        cur = conn.execute(
            f"SELECT id, name, kind, url, enabled FROM sources {where} ORDER BY name ASC"
        )
        return cur.fetchall()
    finally:
        if close_later:
            conn.close()

def add_taxonomy_item(name: str, parent_id: Optional[int] = None,
                      conn: Optional[sqlite3.Connection] = None) -> int:
    """
    Inserta una categoría si no existe (coincidencia por name+parent_id). Devuelve id.
    Nota: cuando introduzcamos 'slug' único, migraremos a ese criterio.
    """
    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        with conn:
            row = conn.execute(
                "SELECT id FROM taxonomy WHERE name = ? AND (parent_id IS ? OR parent_id = ?)",
                (name, parent_id, parent_id)
            ).fetchone()
            if row:
                return int(row["id"])
            cur = conn.execute(
                "INSERT INTO taxonomy(name, parent_id) VALUES (?, ?)",
                (name, parent_id)
            )
            return int(cur.lastrowid)
    finally:
        if close_later:
            conn.close()

def get_taxonomy(conn: Optional[sqlite3.Connection] = None) -> List[sqlite3.Row]:
    """
    Devuelve categorías registradas.
    """
    close_later = False
    if conn is None:
        conn, close_later = get_conn(), True
    try:
        cur = conn.execute(
            "SELECT id, name, parent_id FROM taxonomy ORDER BY name ASC"
        )
        return cur.fetchall()
    finally:
        if close_later:
            conn.close()
def reclassify_by_source(conn):
    """
    Reclasifica artículos que sigan en 'OTROS' según la fuente.
    Devuelve el número de filas actualizadas.
    """
    updates = [
        ("TECNOLOGIA",  "Reddit r/technology%"),
        ("TECNOLOGIA",  "Reddit r/Futurology%"),
        ("VIDEOJUEGOS", "Reddit r/gaming%"),
        ("TECNOLOGIA",  "Xataka%"),
        ("TECNOLOGIA",  "MIT Tech Review%"),
        ("CIENCIA",     "NASA%"),
        ("TECNOLOGIA",  "Wired%"),
        ("CULTURA",     "Reddit r/Latinoamerica%"),
        ("CIENCIA",     "Reddit r/science%"),
        ("ACTUALIDAD",  "Reddit r/worldnews%"),
        ]
    total = 0
    with conn:
        for cat, pattern in updates:
            cur = conn.execute(
                """
                UPDATE articles
                   SET category = ?
                 WHERE (category IS NULL OR UPPER(category) = 'OTROS')
                   AND source LIKE ?
                """,
                (cat, pattern),
            )
            total += cur.rowcount
    return total
