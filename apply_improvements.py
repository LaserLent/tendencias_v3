import sys, os, shutil, re

# --- Config ---
project_dir = sys.argv[1] if len(sys.argv) > 1 else "Buscador de tendencias v3"
filters_path = os.path.join(project_dir, "core", "filters.py")
utils_path = os.path.join(project_dir, "core", "utils.py")
main_path = os.path.join(project_dir, "main.py")

def backup(path):
    if os.path.isfile(path) and not os.path.isfile(path + ".bak"):
        shutil.copy2(path, path + ".bak")

def ensure_parents(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)

# --- Nuevo filters.py (regex + sin acentos) ---
NEW_FILTERS = r'''import re, unicodedata
from config import EXCLUIR_POLITICA

def _normalize(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.lower()

_patterns = [rf"\b{re.escape(_normalize(term))}\b" for term in EXCLUIR_POLITICA if term]
_RE_POL = re.compile("|".join(_patterns)) if _patterns else re.compile(r"$^")  # no coincide nada si lista vacía

def filtrar_politica(titulo: str) -> bool:
    if not titulo:
        return False
    return bool(_RE_POL.search(_normalize(titulo)))
'''

# --- Añadido para utils.py: canonicalize_url ---
UTILS_ADDON = r'''

# --- URL canonicalization (tracking-safe) ---
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

_TRACKING_PARAMS = {
    "utm_source","utm_medium","utm_campaign","utm_term","utm_content",
    "utm_id","utm_name","utm_reader","utm_viz_id","utm_pubreferrer",
    "gclid","fbclid","igshid","mc_cid","mc_eid","spm","vero_conv","vero_id"
}

def canonicalize_url(url: str) -> str:
    if not url:
        return ""
    try:
        u = urlparse(url)
        scheme = "https" if u.scheme in ("http","https","") else u.scheme
        netloc = (u.netloc or "").lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]
        path = (u.path or "").rstrip("/")
        query_pairs = [(k, v) for k, v in parse_qsl(u.query, keep_blank_values=True) if k not in _TRACKING_PARAMS]
        query = urlencode(query_pairs, doseq=True)
        return urlunparse((scheme, netloc, path, "", query, ""))
    except Exception:
        return url  # fail-safe
'''

# --- Enlace en main.py a la versión compartida ---
MAIN_BIND = r'''

# Bind shared canonicalize_url implementation from core.utils
try:
    from core.utils import canonicalize_url as _canon
    canonicalize_url = _canon
except Exception:
    pass
'''

def write_filters():
    ensure_parents(filters_path)
    backup(filters_path)
    with open(filters_path, "w", encoding="utf-8") as f:
        f.write(NEW_FILTERS)

def patch_utils():
    ensure_parents(utils_path)
    if not os.path.exists(utils_path):
        # si no existe, creamos el archivo con solo el addon
        with open(utils_path, "w", encoding="utf-8") as f:
            f.write(UTILS_ADDON.lstrip())
        return "created"
    backup(utils_path)
    with open(utils_path, "r", encoding="utf-8") as f:
        content = f.read()
    if "def canonicalize_url(" in content:
        return "present"
    with open(utils_path, "a", encoding="utf-8") as f:
        if not content.endswith("\n"):
            f.write("\n")
        f.write(UTILS_ADDON)
    return "appended"

def patch_main():
    if not os.path.exists(main_path):
        return "missing"
    backup(main_path)
    with open(main_path, "r", encoding="utf-8") as f:
        content = f.read()
    if "from core.utils import canonicalize_url as _canon" in content:
        return "present"
    with open(main_path, "a", encoding="utf-8") as f:
        if not content.endswith("\n"):
            f.write("\n")
        f.write(MAIN_BIND)
    return "appended"

def main():
    assert os.path.isdir(project_dir), f"No encuentro la carpeta del proyecto: {project_dir}"
    write_filters()
    u = patch_utils()
    m = patch_main()
    print("✔ filters.py reescrito")
    print(f"✔ utils.py: {u}")
    print(f"✔ main.py: {m}")
    print("Hecho. Ejecuta tu app con `python main.py`.")

if __name__ == "__main__":
    main()
