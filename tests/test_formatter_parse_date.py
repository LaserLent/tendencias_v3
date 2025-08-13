from datetime import datetime
from core.formatter import _parse_date

def _same_hm(a: datetime, h: int, m: int):
    assert a.hour == h and a.minute == m

def test_iso_with_offset_keeps_local_clock_in_madrid():
    dt = _parse_date('2025-08-13T18:32:12+02:00')
    assert dt is not None and (getattr(dt.tzinfo, 'key', '') == 'Europe/Madrid')
    _same_hm(dt, 18, 32)

def test_rfc2822_gmt_converts_to_madrid():
    dt = _parse_date('Wed, 13 Aug 2025 16:32:12 GMT')
    assert dt is not None and (getattr(dt.tzinfo, 'key', '') == 'Europe/Madrid')
    # 16:32 UTC => 18:32 CEST
    _same_hm(dt, 18, 32)

def test_rfc2822_numeric_tz_parsed_and_converted():
    dt = _parse_date('13 Aug 2025 16:32:12 +0000')
    assert dt is not None and (getattr(dt.tzinfo, 'key', '') == 'Europe/Madrid')
    _same_hm(dt, 18, 32)

def test_naive_is_assumed_madrid_without_shift():
    dt = _parse_date('2025-08-13 16:32:12')
    assert dt is not None and (getattr(dt.tzinfo, 'key', '') == 'Europe/Madrid')
    _same_hm(dt, 16, 32)

def test_invalid_returns_none():
    assert _parse_date('Invalid/garbage') is None