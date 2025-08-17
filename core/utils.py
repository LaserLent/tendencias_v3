import json, re
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
PROFILE_JSON = "canal_brief_master_v39.json"

def _load_profile():
    p = Path(PROFILE_JSON)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)

_taxonomy_cache = None

def load_taxonomy():
    global _taxonomy_cache
    if _taxonomy_cache is not None:
        return _taxonomy_cache
    data = _load_profile()
    taxonomy = {}
    td = data.get("topic_discovery", {}).get("topic_taxonomy", [])
    for item in td:
        cid = item.get("id", "OTROS").upper()
        includes = item.get("include", []) or []
        kws = set(k.lower() for k in includes if k)
        taxonomy[cid] = list(kws)
    english_map = data.get("topic_discovery", {}).get("english_to_es", {}) or {}
    for eng, es in english_map.items():
        eng = eng.lower(); es = es.lower()
        for cid, kws in taxonomy.items():
            if es in kws and eng not in kws:
                kws.append(eng)
    _taxonomy_cache = taxonomy
    return taxonomy

import re as _re
def classify_by_taxonomy(title: str, taxonomy=None):
    if not title:
        return "OTROS"
    if taxonomy is None:
        taxonomy = load_taxonomy()
    t = title.lower()
    best = None; best_count = 0
    for cid, kws in taxonomy.items():
        if not kws:
            continue
        cnt = 0
        for kw in kws:
            if not kw:
                continue
            if _re.search(rf"\b{re.escape(kw)}\b", t):
                cnt += 1
        if cnt > best_count:
            best = cid; best_count = cnt
    return best if best_count > 0 else "OTROS"

def humanize_category(cat_id: str) -> str:
    if not cat_id:
        return "Otros"
    parts = cat_id.split("_")
    parts = [p.upper() if len(p) <= 2 else p.capitalize() for p in parts]
    return " ".join(parts)


# --- URL canonicalization (tracking-safe) ---
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

_TRACKING_PARAMS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content",
    "utm_id","utm_name","utm_reader","utm_viz_id","utm_pubreferrer",
    "gclid","fbclid","igshid","mc_cid","mc_eid","spm","vero_conv","vero_id"
}

# Añade arriba:
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Reemplaza la función por esta versión robusta:
def canonicalize_url(u: str) -> str:
    if not u:
        return ""
    try:
        p = urlparse(u.strip())

        scheme = (p.scheme or "").lower()
        host = (p.hostname or "").lower()
        port = p.port
        # quita puertos por defecto
        if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
            netloc = f"{host}:{port}"
        else:
            netloc = host

        # --- limpiar query ---
        TRACKING_PREFIXES = ("utm",)   # <— ojo: 'utm' a secas y cualquier 'utm*'
        TRACKING_KEYS = {
            "gclid","fbclid","igshid","mc_cid","mc_eid",
            "ref_src","ref_url","spm","si","siid","mkt_tok"
        }

        kept = []
        for k, v in parse_qsl(p.query, keep_blank_values=True):
            lk = k.lower()
            # elimina si es 'utm' o empieza por 'utm' (utm, utm_source, utmX, etc.) o si está en lista
            if lk == "utm" or lk.startswith(TRACKING_PREFIXES) or lk in TRACKING_KEYS:
                continue
            kept.append((k, v))

        # orden estable
        kept.sort(key=lambda kv: (kv[0], kv[1]))
        query = urlencode(kept, doseq=True)

        # sin fragmento
        fragment = ""

        # conserva la ruta (si está vacía, pon '/')
        path = p.path or "/"

        return urlunparse((scheme, netloc, path, p.params, query, fragment))
    except Exception:
        return u.strip()