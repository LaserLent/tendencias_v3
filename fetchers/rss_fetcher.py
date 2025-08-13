import feedparser
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from email.utils import parsedate_to_datetime
import logging
from config import RSS_FEEDS, MAX_HORAS
from core.filters import filtrar_politica
from core.utils import load_taxonomy, classify_by_taxonomy
from core.formatter import _parse_date

logger = logging.getLogger(__name__)

def _parse_entry_date(entry):
    try:
        struct = entry.get('published_parsed') or entry.get('updated_parsed')
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)
    except Exception:
        pass
    text = entry.get('published') or entry.get('updated') or ''
    if text:
        try:
            dt = parsedate_to_datetime(text)
            if dt is None:
                return None
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None

def obtener_noticias_recientes(max_por_categoria=5):
    ahora = datetime.now(timezone.utc)
    cutoff = ahora - timedelta(hours=MAX_HORAS)
    try:
        taxonomy = load_taxonomy()
    except Exception:
        taxonomy = None
    resultados = []
    for cfg_categoria, nombre, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
        except Exception as e:
            logger.warning('[RSS] error leyendo %s: %s', url, e)
            continue
        for entry in feed.entries:
            fecha_pub = _parse_entry_date(entry)
            fecha_dt = _parse_date(fecha_pub)
            if not fecha_dt or fecha_dt < cutoff:
                continue
            titulo = (entry.get('title') or '').strip()
            if not titulo:
                continue
            try:
                if filtrar_politica(titulo):
                    continue
            except Exception:
                pass
            categoria_detectada = None
            try:
                if taxonomy:
                    categoria_detectada = classify_by_taxonomy(titulo, taxonomy)
            except Exception:
                categoria_detectada = None
            categoria_final = categoria_detectada or cfg_categoria or 'OTROS'
            enlace = entry.get('link') or entry.get('id') or ''
            noticia = {
                'titulo': titulo or 'Sin título',
                'link': enlace,
                'fecha': fecha_dt.isoformat(),
                'fuente': nombre,
                'categoria': categoria_final
            }
            resultados.append(noticia)
    por_cat = defaultdict(list)
    for n in resultados:
        por_cat[n['categoria']].append(n)
    final = []
    for cat, items in por_cat.items():
        items_sorted = sorted(items, key=lambda x: _parse_date(x.get('fecha')).timestamp() if _parse_date(x.get('fecha')) else 0.0, reverse=True)
        final.extend(items_sorted[:max_por_categoria])
    final.sort(key=lambda x: _parse_date(x.get('fecha')).timestamp() if _parse_date(x.get('fecha')) else 0.0, reverse=True)
    return final
