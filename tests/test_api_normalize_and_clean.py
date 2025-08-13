import importlib
from core.text_clean import clean_text
import api.app as app  # usamos su normalizador interno

def test_clean_text_mojibake_y_entidades():
    raw = "Study: Social media probably canâ€™t be fixed &amp; NOâ\u2082 …"
    cleaned = clean_text(raw)
    assert "can't" in cleaned      # ’ -> '
    assert "&" in cleaned          # &amp; -> &
    assert ("NO₂" in cleaned) or ("NO2" in cleaned)
    assert ("…" in cleaned) or ("..." in cleaned)

def test_safe_normalize_repara_url_reddit_relativa():
    rec = {
        "titulo": "Post",
        "link": "/r/es/comments/abc123/un_titulo/",
        "fecha": "2025-08-13T00:00:00+02:00",
        "fuente": "Reddit r/es",
        "categoria": "OTROS",
    }
    norm = app._safe_normalize(rec)
    assert norm is not None
    assert norm["url"].startswith("https://www.reddit.com/r/es/comments/abc123/un_titulo/")
    assert "reddit.com/r/es/comments/abc123/un_titulo" in norm["canonical_url"]