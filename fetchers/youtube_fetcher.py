import os, time, logging
from datetime import datetime, timezone, timedelta
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import config
from core.utils import load_taxonomy, classify_by_taxonomy
from core.filters import filtrar_politica
from core.formatter import _parse_date

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

def obtener_de_youtube():
    api_key = os.environ.get('YOUTUBE_API_KEY') or getattr(config, 'YOUTUBE_API_KEY', '') or ''
    if not api_key:
        logger.info('[YouTube] clave API no configurada o placeholder. Omitiendo YouTube.')
        return []
    taxonomy = load_taxonomy()
    ahora = datetime.now(timezone.utc)
    cutoff = ahora - timedelta(hours=getattr(config, 'MAX_HORAS', 24))
    out = []
    try:
        youtube = build('youtube', 'v3', developerKey=api_key, cache_discovery=False)
    except Exception as e:
        logger.error('YouTube client init error: %s', e)
        return []
    for region in getattr(config, 'YT_REGIONS', ['ES']):
        try:
            resp = youtube.videos().list(
                part='snippet,statistics',
                chart='mostPopular',
                regionCode=region,
                maxResults=getattr(config, 'MAX_YT_RESULTS', 8)
            ).execute()
            for it in resp.get('items', []):
                snip = it.get('snippet', {})
                titulo = (snip.get('title') or '').strip()
                if filtrar_politica(titulo):
                    continue
                pub = snip.get('publishedAt')
                if not pub:
                    continue
                try:
                    fecha_utc = datetime.fromisoformat(pub.replace('Z', '+00:00')).astimezone(timezone.utc)
                except Exception:
                    fecha_utc = datetime.now(timezone.utc)
                fecha_dt = _parse_date(fecha_utc)
                if not fecha_dt or fecha_dt < cutoff:
                    continue
                categoria = classify_by_taxonomy(titulo, taxonomy)
                noticia = {
                    'titulo': titulo or 'Sin título',
                    'link': f"https://youtu.be/{it.get('id')}",
                    'fecha': fecha_dt.isoformat(),
                    'fuente': f"YouTube ({region})",
                    'categoria': categoria
                }
                out.append(noticia)
            time.sleep(0.2)
        except HttpError as he:
            logger.error('YouTube HttpError %s: %s', region, he)
        except Exception as e:
            logger.exception('YouTube error %s: %s', region, e)
    def _ts(item):
        dt = _parse_date(item.get('fecha'))
        return dt.timestamp() if dt else 0.0
    out.sort(key=_ts, reverse=True)
    return out
