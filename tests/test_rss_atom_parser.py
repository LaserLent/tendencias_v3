import types
from services import ingest as ing

class FakeResp:
    def __init__(self, data: bytes): self._d = data
    def read(self): return self._d
    def __enter__(self): return self
    def __exit__(self, *a): pass

def test_rss2_basic(monkeypatch):
    rss = b"""<?xml version="1.0"?>
    <rss version="2.0"><channel>
      <item><title>One</title><link>https://ex.com/1</link><pubDate>Fri, 15 Aug 2025 10:30:00 GMT</pubDate></item>
      <item><title>Two</title><link>/2</link><pubDate>Fri, 15 Aug 2025 11:00:00 GMT</pubDate></item>
    </channel></rss>"""
    monkeypatch.setattr(ing.urllib.request, "urlopen", lambda req, timeout=15: FakeResp(rss), raising=True)
    out = list(ing._fetch_rss_items_simple("https://ex.com/feed"))
    assert len(out) == 2
    assert out[0]["title"] == "One"
    assert out[0]["url"] == "https://ex.com/1"
    assert out[1]["url"].startswith("https://ex.com/")  # relative -> absolute
    assert out[0]["date"] and out[1]["date"]

def test_atom_basic(monkeypatch):
    atom = b"""<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <title>Atom One</title>
        <link href="https://ex.com/a1" rel="alternate"/>
        <updated>2025-08-15T12:00:00Z</updated>
      </entry>
    </feed>"""
    monkeypatch.setattr(ing.urllib.request, "urlopen", lambda req, timeout=15: FakeResp(atom), raising=True)
    out = list(ing._fetch_rss_items_simple("https://ex.com/feed"))
    assert len(out) == 1
    assert out[0]["title"] == "Atom One"
    assert out[0]["url"] == "https://ex.com/a1"
    assert out[0]["date"].startswith("2025-08-15")
