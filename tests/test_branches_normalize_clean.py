import core.normalize as norm
from core.text_clean import clean_text

def test_to_canonical_retorna_none_si_no_dict():
    assert norm.to_canonical(None) is None
    assert norm.to_canonical("no es dict") is None
    assert norm.to_canonical(123) is None

def test_to_canonical_fallback_si_canonicalize_falla(monkeypatch):
    def boom(_u): raise RuntimeError('boom')
    # parcheamos la función importada en el módulo normalize
    monkeypatch.setattr(norm, 'canonicalize_url', boom)
    rec = {
        'titulo': 't',
        'link': 'https://EXAMPLE.com/a?x=1',
        'fecha': '2025-01-01T00:00:00+00:00',
        'fuente': 'X',
    }
    out = norm.to_canonical(rec)
    assert out is not None
    # como falló canonicalize_url, debe caer al url original
    assert out['canonical_url'] == rec['link']

def test_clean_text_none_y_espacios():
    assert clean_text(None) == ''
    assert clean_text('  a   b   ') == 'a b'