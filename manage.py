from __future__ import annotations
import argparse, json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from core.db import init_db, get_conn, upsert_article, get_stats
from core.utils import canonicalize_url
from core.text_clean import clean_text
from core.formatter import _parse_date

DATA_DIR = Path('data')
TAX_FILE = DATA_DIR / 'taxonomy.json'
OUT_FILE = DATA_DIR / 'output.json'

def _iso_or_none(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    try:
        dt = _parse_date(s)
        return dt.isoformat() if dt else None
    except Exception:
        return None

def cmd_init_db(args):
    init_db()
    print('OK: esquema creado/actualizado.')

def cmd_load_taxonomy(args):
    p = Path(args.file) if args.file else TAX_FILE
    if not p.exists():
        print(f'WARN: no existe {p}')
        return
    raw = json.loads(p.read_text(encoding='utf-8'))
    added = 0
    with get_conn() as conn:
        existing = {r['name'] for r in conn.execute('SELECT name FROM taxonomy')}
        def add(name: str, parent_id: Optional[int] = None) -> int:
            nonlocal added, existing
            name = clean_text(str(name or '')).strip()
            if not name or name in existing:
                return 0
            if parent_id is None:
                conn.execute('INSERT INTO taxonomy(name) VALUES (?)', (name,))
            else:
                conn.execute('INSERT INTO taxonomy(name,parent_id) VALUES (?,?)', (name, parent_id))
            existing.add(name)
            added += 1
            return 1

        if isinstance(raw, list):
            for x in raw:
                add(x)
        elif isinstance(raw, dict):
            # Soporta {"categories":[...]} o {"CIENCIA":[...], "TECNOLOGIA":[...], ...}
            if 'categories' in raw and isinstance(raw['categories'], list):
                for x in raw['categories']:
                    add(x)
            else:
                for k, v in raw.items():
                    add(k)
                    if isinstance(v, list):
                        pid = conn.execute('SELECT id FROM taxonomy WHERE name=?', (clean_text(str(k)).strip(),)).fetchone()
                        if pid:
                            for child in v:
                                add(child, pid[0])
        else:
            print('WARN: formato de taxonomy.json no reconocido; no se insertó nada.')
    print(f'OK: taxonomía añadida: +{added}')

def _iter_output_items(obj: Any) -> Iterable[Dict[str, Any]]:
    # Acepta lista directa o {"value":[...]} como la que imprime main.py
    if isinstance(obj, list):
        yield from obj
    elif isinstance(obj, dict) and isinstance(obj.get('value'), list):
        yield from obj['value']
    else:
        return

def cmd_import_output(args):
    p = Path(args.file) if args.file else OUT_FILE
    if not p.exists():
        print(f'WARN: no existe {p}')
        return
    data = json.loads(p.read_text(encoding="utf-8"))
    ins, upd, tot = 0, 0, 0
    with get_conn() as conn:
        for it in _iter_output_items(data):
            tot += 1
            title = clean_text(it.get('titulo') or it.get('title') or '')
            url   = it.get('link') or it.get('url') or ''
            can   = None
            try:
                can = canonicalize_url(url)
            except Exception:
                can = url or ''
            date  = _iso_or_none(it.get('fecha') or it.get('date'))
            src   = clean_text(it.get('fuente') or it.get('source') or '')
            cat   = clean_text(it.get('categoria') or it.get('category') or 'OTROS')
            rec = {
                "title": title, "url": url, "canonical_url": can,
                "date": date, "source": src, "category": cat
            }
            inserted = upsert_article(rec, conn=conn)
            if inserted: ins += 1
            else: upd += 1
    print(f'OK: import-output => total:{tot} inserted:{ins} updated:{upd}')

def cmd_stats(args):
    s = get_stats()
    print(json.dumps(s, ensure_ascii=False, indent=2))

def cmd_vacuum(args):
    with get_conn() as conn:
        conn.execute('VACUUM')
    print('OK: VACUUM ejecutado.')

def main():
    ap = argparse.ArgumentParser(prog='manage.py', description='Gestión de base de datos')
    sp = ap.add_subparsers(dest='cmd', required=True)

    sp.add_parser('init-db')
    ptx = sp.add_parser('load-taxonomy'); ptx.add_argument('--file')
    pout = sp.add_parser('import-output'); pout.add_argument('--file')
    sp.add_parser('stats')
    sp.add_parser('vacuum')

    args = ap.parse_args()
    if args.cmd == 'init-db': cmd_init_db(args)
    elif args.cmd == 'load-taxonomy': cmd_load_taxonomy(args)
    elif args.cmd == 'import-output': cmd_import_output(args)
    elif args.cmd == 'stats': cmd_stats(args)
    elif args.cmd == 'vacuum': cmd_vacuum(args)

if __name__ == '__main__':
    main()