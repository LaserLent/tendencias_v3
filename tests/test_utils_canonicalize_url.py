from urllib.parse import urlparse, parse_qs
from core.utils import canonicalize_url

def test_canonicalize_url_sin_tracking_y_host_minusculas():
    url = "https://Example.COM/Path/Sub?utm_source=x&utm_medium=y&fbclid=123&gclid=abc&x=1"
    can = canonicalize_url(url)
    p = urlparse(can)
    # Host debe estar en minúsculas
    assert p.netloc == "example.com"
    # No deben quedar parámetros de tracking
    qs = parse_qs(p.query)
    assert not any(k.startswith("utm_") for k in qs.keys())
    assert "fbclid" not in qs and "gclid" not in qs

def test_canonicalize_url_idempotente():
    u = "https://example.com/a?utm_campaign=z&b=2"
    assert canonicalize_url(canonicalize_url(u)) == canonicalize_url(u)
