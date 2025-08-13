import requests, time, logging
from datetime import datetime, timezone, timedelta
import config
from core.utils import load_taxonomy, classify_by_taxonomy
from core.filters import filtrar_politica
from core.formatter import _parse_date

logger = logging.getLogger(__name__)
REDDIT_SUBREDDITS = getattr(config, 'REDDIT_SUBREDDITS', ['technology','Futurology','gaming'])
MAX_HORAS = getattr(config, 'MAX_HORAS', 24)
MAX_ITEMS_REDDIT = getattr(config, 'MAX_ITEMS_REDDIT', 200)
REDDIT_LIMIT = getattr(config, 'REDDIT_LIMIT', 25)
HEADERS = {'User-Agent': 'canal_brief_bot/0.1 (by u/youremail)'}

def obtener_de_reddit(limit_per_sub=REDDIT_LIMIT):
    ahora = datetime.now(timezone.utc)
    cutoff = ahora - timedelta(hours=MAX_HORAS)
    out = []
    taxonomy = load_taxonomy()
    session = requests.Session()
    session.headers.update(HEADERS)
    for sub in REDDIT_SUBREDDITS:
        url = f'https://www.reddit.com/r/{sub}/new.json?limit={limit_per_sub}'
        try:
            r = session.get(url, timeout=10)
            if r.status_code != 200:
                logger.warning('Reddit %s status %s', sub, r.status_code)
                time.sleep(0.5)
                continue
            data = r.json()
            for c in data.get('data', {}).get('children', []):
                d = c.get('data', {})
                if d.get('over_18'):
                    continue
                titulo = (d.get('title') or '').strip()
                if filtrar_politica(titulo):
                    continue
                ts = d.get('created_utc')
                if not ts:
                    continue
                fecha_utc = datetime.fromtimestamp(int(ts), tz=timezone.utc)
                fecha_dt = _parse_date(fecha_utc)
                if not fecha_dt or fecha_dt < cutoff:
                    continue
                categoria = classify_by_taxonomy(titulo, taxonomy)
                noticia = {
                    'titulo': titulo or 'Sin título',
                    'link': d.get('url') or f"https://reddit.com{d.get('permalink','')}",
                    'fecha': fecha_dt.isoformat(),
                    'fuente': f'Reddit r/{sub}',
                    'categoria': categoria
                }
                out.append(noticia)
            time.sleep(0.6)
        except Exception:
            logger.exception('Reddit error %s', sub)
    def _ts(item):
        dt = _parse_date(item.get('fecha'))
        return dt.timestamp() if dt else 0.0
    out.sort(key=_ts, reverse=True)
    maxr = MAX_ITEMS_REDDIT if 'MAX_ITEMS_REDDIT' in globals() else 200
    return out[:maxr]
