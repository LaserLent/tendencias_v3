from urllib.parse import urlparse, parse_qs
from core.normalize import to_canonical
from core.utils import canonicalize_url

def test_to_canonical_es_keys_ok():
    rec = {
        "titulo": "Título ES",
        "link": "https://Example.COM/a?utm_source=x&utm_medium=y&fbclid=123&b=2",
        "fecha": "2025-08-13T12:00:00+02:00",
        "fuente": "Reddit r/technology",
        "categoria": "OTROS",
    }
    can = to_canonical(rec)
    assert can is not None
    assert can["title"] == "Título ES"
    assert can["url"].startswith("https://Example.COM/a")
    # canonical_url debe tener host en minúsculas y sin parámetros de tracking
    p = urlparse(can["canonical_url"])
    assert p.scheme in ("http","https")
    assert p.netloc == "example.com"
    qs = parse_qs(p.query)
    assert not any(k.startswith("utm_") for k in qs)
    assert "fbclid" not in qs
    assert qs.get("b") == ["2"]
    assert can["date"] == "2025-08-13T12:00:00+02:00"
    assert can["source"] == "Reddit r/technology"
    assert can["category"] == "OTROS"

def test_to_canonical_missing_fields_returns_none():
    rec = {"titulo": "", "link": "https://example.com", "fecha": "2025-01-01", "fuente": "X"}
    assert to_canonical(rec) is None

def test_to_canonical_category_non_string_is_stringified():
    rec = {
        "titulo": "ok",
        "link": "https://example.com",
        "fecha": "2025-01-01T00:00:00+00:00",
        "fuente": "X",
        "categoria": ["A","B"],
    }
    can = to_canonical(rec)
    assert isinstance(can["category"], str)

def test_canonicalize_url_strips_tracking_and_lowercases_host():
    u = "https://Example.COM/Path/Sub?utm_campaign=z&utm_source=x&fbclid=1&gclid=2&b=2"
    cu = canonicalize_url(u)
    p = urlparse(cu)
    assert p.netloc == "example.com"
    qs = parse_qs(p.query)
    assert "b" in qs and qs["b"] == ["2"]
    assert not any(k.startswith("utm_") for k in qs)
    assert "fbclid" not in qs and "gclid" not in qs