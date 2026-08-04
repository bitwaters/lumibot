import time

from lumibot.models import Source, TokenCandidate
from lumibot.pipeline import ChainPipeline


def _cand(source: Source, addr: str = "tok") -> TokenCandidate:
    return TokenCandidate(chain="sol", address=addr, source=source, signal_type=12)


def test_mark_dual_source_within_ttl(monkeypatch):
    pipe = object.__new__(ChainPipeline)
    pipe._recent_sources = {}
    pipe._dual_source_ttl_sec = 30.0

    a = _cand(Source.SIGNAL)
    pipe._mark_dual_source(a)
    assert a.dual_source is False

    b = _cand(Source.TRENDING)
    pipe._mark_dual_source(b)
    assert b.dual_source is True

    # Expired other source → not dual
    pipe._recent_sources["tok"]["signal"] = time.time() - 60
    c = _cand(Source.TRENDING)
    pipe._mark_dual_source(c)
    assert c.dual_source is False
