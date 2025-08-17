from core.utils import canonicalize_url
from urllib.parse import urlparse, parse_qs

def test_canonical_removes_tracking_and_sorts_query():
    a = "https://EXAMPLE.com/path?p=1&utm_source=x&b=2#frag"
    b = "https://example.com:443/path?b=2&p=1"
    assert canonicalize_url(a) == canonicalize_url(b)

def test_canonical_drops_fbclid_and_default_ports():
    a = "http://site.com:80/x?fbclid=zzz&id=42"
    b = "http://site.com/x?id=42"
    assert canonicalize_url(a) == canonicalize_url(b)

def test_canonical_keeps_non_tracking_params_ordered():
    a = "https://s.com/a?z=2&y=1&utm_campaign=c"
    b = "https://s.com/a?y=1&z=2"
    assert canonicalize_url(a) == canonicalize_url(b)

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
