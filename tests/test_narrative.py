import pytest

from lumibot.config import NarrativeCfg
from lumibot.models import Source, TokenCandidate
from lumibot.narrative import NarrativeCache, NarrativeService


def _cfg(**overrides) -> NarrativeCfg:
    base = dict(
        enabled=True,
        base_url="https://fake.deepseek",
        model="deepseek-chat",
        timeout_sec=10,
        min_symbol_len=3,
        symbol_blocklist=[],
        cache_ttl_sec=3600,
    )
    base.update(overrides)
    return NarrativeCfg(**base)


def _cand(symbol="TRUMP", name="OFFICIAL TRUMP", address="tok") -> TokenCandidate:
    return TokenCandidate(
        chain="sol", address=address, source=Source.SIGNAL, symbol=symbol, name=name
    )


class FakeNarrativeClient:
    def __init__(self, content: str, *, fail: bool = False) -> None:
        self.content = content
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    async def complete(self, *, system: str, user: str) -> dict:
        self.calls.append((system, user))
        if self.fail:
            raise RuntimeError("llm down")
        return {"choices": [{"message": {"content": self.content}}]}


@pytest.mark.asyncio
async def test_narrative_normal_flow_and_cache():
    client = FakeNarrativeClient('{"narrative": "特朗普概念官方迷因币"}')
    svc = NarrativeService("sk-test", _cfg())
    svc.client = client  # type: ignore[assignment]

    cand = _cand()
    info = {"link": {"description": "Trump official", "website": "https://gettrumpmemes.com"}}
    first = await svc.narrative_for(cand, info)
    assert first == "特朗普概念官方迷因币"
    assert len(client.calls) == 1
    # cache hit: no second LLM call
    second = await svc.narrative_for(cand, info)
    assert second == first
    assert len(client.calls) == 1
    # prompt contains inputs
    assert "symbol=TRUMP" in client.calls[0][1]
    assert "gettrumpmemes.com" in client.calls[0][1]


@pytest.mark.asyncio
async def test_narrative_na_not_cached_and_none():
    client = FakeNarrativeClient('{"narrative": "N/A"}')
    svc = NarrativeService("sk-test", _cfg())
    svc.client = client  # type: ignore[assignment]
    assert await svc.narrative_for(_cand(), {}) is None
    # N/A is not cached -> second call hits LLM again
    assert await svc.narrative_for(_cand(), {}) is None
    assert len(client.calls) == 2


@pytest.mark.asyncio
async def test_narrative_failure_returns_none():
    svc = NarrativeService("sk-test", _cfg())
    svc.client = FakeNarrativeClient("", fail=True)  # type: ignore[assignment]
    assert await svc.narrative_for(_cand(), {}) is None


@pytest.mark.asyncio
async def test_short_symbol_and_blocklist_skipped():
    svc = NarrativeService("sk-test", _cfg())
    svc.client = FakeNarrativeClient('{"narrative": "x"}')  # type: ignore[assignment]
    # short symbol
    assert await svc.narrative_for(_cand(symbol="X"), {}) is None
    # blocklisted (case-insensitive)
    svc = NarrativeService("sk-test", _cfg(symbol_blocklist=["TRUMP"]))
    svc.client = FakeNarrativeClient('{"narrative": "x"}')  # type: ignore[assignment]
    assert await svc.narrative_for(_cand(symbol="trump"), {}) is None
    assert len(svc.client.calls) == 0  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_truncation_and_plain_text_fallback():
    long_text = "很" * 50
    client = FakeNarrativeClient(f'{{"narrative": "{long_text}"}}')
    svc = NarrativeService("sk-test", _cfg())
    svc.client = client  # type: ignore[assignment]
    out = await svc.narrative_for(_cand(), {})
    assert out is not None and len(out) <= 30

    # plain text without JSON wrapper also parses
    svc2 = NarrativeService("sk-test", _cfg())
    svc2.client = FakeNarrativeClient("AI Agent 概念")  # type: ignore[assignment]
    assert await svc2.narrative_for(_cand(symbol="AGENT", address="a2"), {}) == "AI Agent 概念"


def test_cache_ttl_expiry():
    cache = NarrativeCache(ttl_sec=0)
    cache.set("sol", "t", "叙事")
    assert cache.get("sol", "t") is None
    cache2 = NarrativeCache(ttl_sec=3600)
    cache2.set("sol", "t", "叙事")
    assert cache2.get("sol", "t") == "叙事"
    assert cache2.get("sol", "other") is None
