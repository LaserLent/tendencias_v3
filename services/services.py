from typing import Optional, List, Dict
from datetime import datetime
from core.utils import humanize_category
from core.formatter import guardar_json
from fetchers.rss_fetcher import obtener_noticias_recientes
from fetchers.reddit_fetcher import obtener_de_reddit
from fetchers.youtube_fetcher import obtener_de_youtube

def buscar_articulos(category: Optional[str] = None, date_from: Optional[datetime] = None, date_to: Optional[datetime] = None, text: Optional[str] = None, limit: int = 50) -> List[Dict]:
    resultados = []
    resultados.extend(obtener_noticias_recientes())
    resultados.extend(obtener_de_reddit())
    resultados.extend(obtener_de_youtube())
    # simple filtering by provided params
    if category:
        resultados = [a for a in resultados if a.get('categoria') == category]
    if text:
        resultados = [a for a in resultados if text.lower() in a.get('titulo','').lower()]
    resultados.sort(key=lambda x: x.get('fecha', ''), reverse=True)
    return resultados[:limit]
