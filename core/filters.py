import re, unicodedata
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
