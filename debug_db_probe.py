from core.db import get_conn
with get_conn() as conn:
    total = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
    tc = conn.execute("SELECT COUNT(*) FROM articles WHERE lower(source) LIKE '%techcrunch%'").fetchone()[0]
    print("TOTAL=", total, "TECHCRUNCH_MATCH=", tc)
    print("--- Últimos 5 por fecha ---")
    rows = conn.execute("""
        SELECT title, source, date
        FROM articles
        ORDER BY (date IS NULL) ASC, date DESC, id DESC
        LIMIT 5
    """).fetchall()
    for r in rows:
        print(f"{r['date']} | {r['source']} | {r['title']}")
