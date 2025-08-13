from datetime import datetime
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union
try:
    from zoneinfo import ZoneInfo
    TZ_SP = ZoneInfo('Europe/Madrid'); TZ_UTC = ZoneInfo('UTC')
except Exception:
    import pytz
    TZ_SP = pytz.timezone('Europe/Madrid'); TZ_UTC = pytz.UTC
from core.utils import humanize_category
try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except Exception:
    HAS_DATEUTIL = False

def _parse_date(fecha_raw: Any) -> Optional[datetime]:
    if not fecha_raw:
        return None
    if isinstance(fecha_raw, datetime):
        dt = fecha_raw
    else:
        s = str(fecha_raw).strip()
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        dt = None
        if HAS_DATEUTIL:
            try:
                dt = dateutil_parser.parse(s)
            except Exception:
                dt = None
        if dt is None:
            try:
                dt = datetime.fromisoformat(s)
            except Exception:
                dt = None
        if dt is None:
            fmts = ['%a, %d %b %Y %H:%M:%S %z','%Y-%m-%dT%H:%M:%S%z','%Y-%m-%d %H:%M:%S','%Y-%m-%d']
            for fmt in fmts:
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except Exception:
                    continue
            if dt is None:
                return None
    if getattr(dt, 'tzinfo', None) is None:
        try:
            dt = dt.replace(tzinfo=TZ_UTC)
        except Exception:
            pass
    try:
        dt_sp = dt.astimezone(TZ_SP)
    except Exception:
        try:
            dt = dt.replace(tzinfo=TZ_UTC)
            dt_sp = dt.astimezone(TZ_SP)
        except Exception:
            return dt
    return dt_sp

def formatear_fecha(fecha_str: Any) -> str:
    dt = _parse_date(fecha_str)
    if not dt:
        return str(fecha_str) if fecha_str else ''
    tz_name = dt.strftime('%Z') if dt.strftime('%Z') else ''
    return dt.strftime(f"%d/%m/%Y %H:%M {tz_name}").strip()

def _normalizar_noticia(n: Dict[str, Any]) -> Dict[str, Any]:
    titulo = n.get('titulo') or n.get('tema') or n.get('title') or ''
    link = n.get('link') or n.get('url') or n.get('enlace') or ''
    fecha = n.get('fecha') or n.get('published') or n.get('publishedAt') or ''
    fuente = n.get('fuente') or n.get('subfuente') or n.get('source') or ''
    categoria = n.get('categoria') or n.get('categoria_id') or n.get('categoria_nombre') or n.get('category') or 'OTROS'
    return {'titulo': titulo, 'link': link, 'fecha': fecha, 'fuente': fuente, 'categoria': categoria, **{k: v for k, v in n.items() if k not in ('titulo','tema','title','link','url','enlace','fecha','published','publishedAt','fuente','subfuente','source','categoria','category')}}

def imprimir_en_consola(noticias: Union[Iterable[Dict[str, Any]], Dict[str, Iterable[Dict[str, Any]]]], max_por_categoria: int = 8) -> None:
    cats: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if isinstance(noticias, dict):
        for cat, items in noticias.items():
            for it in items:
                cats[str(cat)].append(_normalizar_noticia(it))
    else:
        for item in noticias:
            n = _normalizar_noticia(item)
            cats.setdefault(str(n.get('categoria', 'OTROS')), []).append(n)
    ordered_cats: List[str] = []
    remaining = [c for c in cats.keys() if c not in ordered_cats]
    remaining_sorted = sorted(remaining, key=lambda c: (-len(cats[c]), c))
    ordered_cats.extend(remaining_sorted)
    for cat in ordered_cats:
        items = cats.get(cat, [])
        if not items:
            continue
        title_cat = humanize_category(cat).upper()
        print(f"\n=== {title_cat} (total: {len(items)}) ===")
        for it in items:
            dt = _parse_date(it.get('fecha'))
            it.setdefault('_ts', dt.timestamp() if dt else 0.0)
        items_sorted = sorted(items, key=lambda x: x.get('_ts', 0.0), reverse=True)[:max_por_categoria]
        for it in items_sorted:
            fecha_fmt = formatear_fecha(it.get('fecha'))
            titulo = it.get('titulo') or 'Sin título'
            fuente = it.get('fuente') or ''
            link = it.get('link') or ''
            if fuente:
                print(f"{fecha_fmt} | {titulo} | {fuente}")
            else:
                print(f"{fecha_fmt} | {titulo}")
            if link:
                print(f"  {link}")
        for it in items:
            if '_ts' in it:
                del it['_ts']

def guardar_json(noticias: Union[Iterable[Dict[str, Any]], Dict[str, Iterable[Dict[str, Any]]]], archivo: str = 'data/output.json') -> None:
    p = Path(archivo)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(noticias, dict):
        data_to_write = {k: [_normalizar_noticia(i) for i in v] for k, v in noticias.items()}
    else:
        data_to_write = [_normalizar_noticia(i) for i in noticias]
    with p.open('w', encoding='utf-8') as f:
        json.dump(data_to_write, f, ensure_ascii=False, indent=2)
# --- v2 de _parse_date: ISO + RFC2822; naive => Europe/Madrid; tz-aware => convertido a Europe/Madrid ---
from datetime import datetime
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
from email.utils import parsedate_to_datetime

def _parse_date_v2(fecha_raw):
    if fecha_raw is None:
        return None
    try:
        s = str(fecha_raw).strip()
        if not s:
            return None
        # Z -> +00:00 para fromisoformat
        s_iso = s.replace('Z', '+00:00')
        dt = None
        # 1) Intento ISO 8601
        try:
            dt = datetime.fromisoformat(s_iso)
        except Exception:
            dt = None
        # 2) Intento RFC 2822 (RSS)
        if dt is None:
            try:
                dt = parsedate_to_datetime(s)
            except Exception:
                dt = None
        if dt is None:
            return None

        # 3) Normalización a Europe/Madrid
        if ZoneInfo:
            TZ_SP = ZoneInfo('Europe/Madrid')
            if dt.tzinfo is None:
                # naive => se asume hora local Europe/Madrid (SIN desplazamiento)
                return dt.replace(tzinfo=TZ_SP)
            else:
                # tz-aware => convertir a Europe/Madrid
                return dt.astimezone(TZ_SP)
        else:
            # Sin zoneinfo: devolver tal cual y evitar crash
            return dt
    except Exception:
        return None

# Aliasing: usamos la v2 como implementación por defecto
_parse_date = _parse_date_v2
