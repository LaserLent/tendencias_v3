# main.py
# Carga opcional de variables desde .env (segura: no falla si falta la librería)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


import logging
from fetchers.rss_fetcher import obtener_noticias_recientes
from fetchers.reddit_fetcher import obtener_de_reddit
from fetchers.youtube_fetcher import obtener_de_youtube
from core.formatter import imprimir_en_consola, guardar_json, _parse_date

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

MAX_TOTAL_ITEMS = 200

def canonicalize_url(url: str) -> str:
    from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
    if not url:
        return ""
    p = urlparse(url)
    scheme = p.scheme or "https"
    netloc = p.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = p.path.rstrip("/")
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.startswith("utm_") and k.lower() != "fbclid"]
    query = urlencode(sorted(q))
    return urlunparse((scheme, netloc, path, "", query, ""))

def dedupe_items(items):
    seen = set()
    deduped = []
    for item in items:
        title = (item.get("titulo") or "").strip().lower()
        url = canonicalize_url(item.get("link") or "")
        key = (title, url)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped

def _fecha_timestamp(item):
    dt = _parse_date(item.get("fecha"))
    return dt.timestamp() if dt else 0.0

def main():
    todas = []
    fetchers = [
        (obtener_noticias_recientes, {"max_por_categoria": 5}),
        (obtener_de_reddit, {}),
        (obtener_de_youtube, {})
    ]
    for fn, kwargs in fetchers:
        try:
            res = fn(**kwargs)
            if isinstance(res, dict):
                for lst in res.values():
                    todas.extend(lst)
            else:
                todas.extend(res or [])
        except Exception as e:
            logger.exception("Error ejecutando fetcher %s: %s", fn.__name__, e)
    if not todas:
        logger.warning("No se han recogido noticias de ninguna fuente.")
        return
    todas = dedupe_items(todas)
    todas = sorted(todas, key=_fecha_timestamp, reverse=True)[:MAX_TOTAL_ITEMS]
    imprimir_en_consola(todas, max_por_categoria=8)
    try:
        guardar_json(todas, archivo="data/output.json")
        logger.info("Guardado data/output.json")
    except Exception as e:
        logger.exception("Error guardando JSON: %s", e)

if __name__ == "__main__":
    main()


# Bind shared canonicalize_url implementation from core.utils
try:
    from core.utils import canonicalize_url as _canon
    canonicalize_url = _canon
except Exception:
    pass
