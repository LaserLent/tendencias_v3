from __future__ import annotations
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse

from core.db import init_db, get_conn, upsert_article, get_stats
from core.utils import canonicalize_url
from core.text_clean import clean_text
from core.formatter import _parse_date

# Rutas por defecto
DATA_DIR = Path("data")
TAX_FILE = DATA_DIR / "taxonomy.json"
OUT_FILE = DATA_DIR / "output.json"


# ---------------------------
# Utilidades comunes
# ---------------------------
def cmd_ingest(args):
    from services.ingest import ingest_now
    stats = ingest_now()
    print(f"OK ingest: collected={stats['collected']} inserted={stats['inserted']} updated={stats['updated']}")

def _iso_or_none(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        dt = _parse_date(s)
        return dt.isoformat() if dt else None
    except Exception:
        return None


def _iter_output_items(obj: Any) -> Iterable[Dict[str, Any]]:
    # Acepta lista directa o {"value":[...]} como la que imprime main.py
    if isinstance(obj, list):
        yield from obj
    elif isinstance(obj, dict) and isinstance(obj.get("value"), list):
        yield from obj["value"]


def _guess_source_label(url: str) -> str:
    try:
        netloc = urlparse(url).netloc
        return netloc or "RSS"
    except Exception:
        return "RSS"


def _to_iso_from_struct(t) -> str:
    try:
        # t suele ser time.struct_time (feedparser). Si falla, devolvemos ahora en UTC
        return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc).isoformat()
    except Exception:
        return datetime.now(timezone.utc).isoformat()


# ---------------------------
# Comandos
# ---------------------------

def cmd_init_db(args) -> None:
    init_db()
    print("OK: esquema creado/actualizado.")


def cmd_load_taxonomy(args) -> None:
    p = Path(args.file) if args.file else TAX_FILE
    if not p.exists():
        print(f"WARN: no existe {p}")
        return

    # BOM-safe
    raw = json.loads(p.read_text(encoding="utf-8-sig"))
    added = 0
    with get_conn() as conn:
        existing = {r["name"] for r in conn.execute("SELECT name FROM taxonomy")}

        def add(name: str, parent_id: Optional[int] = None) -> int:
            nonlocal added, existing
            name = clean_text(str(name or "")).strip()
            if not name or name in existing:
                return 0
            if parent_id is None:
                conn.execute("INSERT INTO taxonomy(name) VALUES (?)", (name,))
            else:
                conn.execute("INSERT INTO taxonomy(name,parent_id) VALUES (?,?)", (name, parent_id))
            existing.add(name)
            added += 1
            return 1

        if isinstance(raw, list):
            for x in raw:
                add(x)
        elif isinstance(raw, dict):
            # Soporta {"categories":[...]} o {"CIENCIA":[...], "TECNOLOGIA":[...], ...}
            if "categories" in raw and isinstance(raw["categories"], list):
                for x in raw["categories"]:
                    add(x)
            else:
                for k, v in raw.items():
                    add(k)
                    if isinstance(v, list):
                        pid = conn.execute(
                            "SELECT id FROM taxonomy WHERE name=?",
                            (clean_text(str(k)).strip(),),
                        ).fetchone()
                        if pid:
                            for child in v:
                                add(child, pid[0])
        else:
            print("WARN: formato de taxonomy.json no reconocido; no se insertó nada.")
    print(f"OK: taxonomía añadida: +{added}")


def cmd_import_output(args) -> None:
    p = Path(args.file) if args.file else OUT_FILE
    if not p.exists():
        print(f"WARN: no existe {p}")
        return
    # BOM-safe
    data = json.loads(p.read_text(encoding="utf-8-sig"))

    ins, upd, tot = 0, 0, 0
    with get_conn() as conn:
        for it in _iter_output_items(data) or []:
            tot += 1
            title = clean_text(it.get("titulo") or it.get("title") or "")
            url = it.get("link") or it.get("url") or ""
            try:
                can = canonicalize_url(url) if url else ""
            except Exception:
                can = url or ""
            date = _iso_or_none(it.get("fecha") or it.get("date"))
            src = clean_text(it.get("fuente") or it.get("source") or "")
            cat = clean_text(it.get("categoria") or it.get("category") or "OTROS")

            rec = {
                "title": title,
                "url": url,
                "canonical_url": can,
                "date": date,
                "source": src,
                "category": cat,
            }
            # upsert_article devuelve True si insertó; False si actualizó/ya existía
            inserted = upsert_article(rec, conn=conn)
            if inserted:
                ins += 1
            else:
                upd += 1
    s = get_stats()
    print(f"OK: import-output => total:{tot} inserted:{ins} updated:{upd} items_total:{s.get('items_total')}")


def cmd_stats(args) -> None:
    s = get_stats()
    print(json.dumps(s, ensure_ascii=False, indent=2))


def cmd_vacuum(args) -> None:
    with get_conn() as conn:
        conn.execute("VACUUM")
    print("OK: VACUUM ejecutado.")


def cmd_import_rss(args) -> None:
    """
    Importa entradas de un RSS a la DB usando upsert_article (dedupe por canonical_url).
    Uso:
      python manage.py import-rss <url> [--category TECNOLOGIA] [--label TechCrunch]
    """
    try:
        import feedparser  # dependencia ligera
    except Exception:
        print("[ERROR] Falta la dependencia 'feedparser'. Instala: python -m pip install feedparser")
        return

    # Normalización consistente con la API
    from api.helpers import normalize as _normalize

    url = args.url
    category = args.category
    label = args.label or _guess_source_label(url)

    print(f"[INFO] Descargando RSS: {url}")
    feed = feedparser.parse(url)
    if getattr(feed, "bozo", 0) and getattr(feed, "bozo_exception", None):
        print("[WARN] RSS bozo:", feed.bozo_exception)

    cnt_ins = cnt_upd = cnt_skip = 0
    with get_conn() as conn:
        for e in getattr(feed, "entries", []) or []:
            raw = {
                "title": getattr(e, "title", "") or "",
                "url": getattr(e, "link", "") or "",
                "date": _to_iso_from_struct(
                    getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
                ),
                "source": label,
                "category": category or None,
            }
            n = _normalize(raw)
            if not n:
                cnt_skip += 1
                continue

            rec = {
                "title": n["title"],
                "url": n["url"],
                "canonical_url": n["canonical_url"],
                "date": n["date"],
                "source": n["source"],
                "category": n.get("category"),
            }
            inserted = upsert_article(rec, conn=conn)
            if inserted:
                cnt_ins += 1
            else:
                cnt_upd += 1

    print(f"[OK] import-rss: inserted={cnt_ins} updated={cnt_upd} skipped={cnt_skip}")


# ---------------------------
# CLI
# ---------------------------

def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="manage.py", description="Gestión de base de datos")
    sp = ap.add_subparsers(dest="cmd", required=True)

    # comandos existentes
    sp.add_parser("init-db")
    ptx = sp.add_parser("load-taxonomy"); ptx.add_argument("--file")
    pout = sp.add_parser("import-output"); pout.add_argument("--file")
    sp.add_parser("stats")
    sp.add_parser("vacuum")

    prs = sp.add_parser("import-rss")
    prs.add_argument("url", help="URL del feed RSS")
    prs.add_argument("--category", help="Categoría opcional (slug/texto)", default=None)
    prs.add_argument("--label", help="Etiqueta de fuente (p. ej. TechCrunch)", default=None)

    # NUEVO: registrar 'ingest' en el MISMO subparsers 'sp'
    sp.add_parser("ingest")

    args = ap.parse_args()

    if args.cmd == "init-db":
        cmd_init_db(args); return 0
    if args.cmd == "load-taxonomy":
        cmd_load_taxonomy(args); return 0
    if args.cmd == "import-output":
        cmd_import_output(args); return 0
    if args.cmd == "stats":
        cmd_stats(args); return 0
    if args.cmd == "vacuum":
        cmd_vacuum(args); return 0
    if args.cmd == "import-rss":
        cmd_import_rss(args); return 0
    if args.cmd == "ingest":               # NUEVO: dispatch
        cmd_ingest(args); return 0

    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
