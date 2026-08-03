import pytest

from lumibot.gmgn.client import EnrichmentCache, GmgnClient, RateLimiter


@pytest.mark.asyncio
async def test_get_price_bypasses_info_cache(monkeypatch):
    client = GmgnClient("k", RateLimiter(10, 10), cache_ttl_sec=300)
    calls = {"n": 0}

    async def fake_request(method, path, *, query=None, body=None, weight=1.0):
        calls["n"] += 1
        return {"price": {"price": str(calls["n"])}}

    monkeypatch.setattr(client, "_request", fake_request)
    # Seed cache with stale price
    client.cache.set("info", "sol", "T", {"price": {"price": "99"}})
    px1 = await client.get_price("sol", "T", "token_info")
    px2 = await client.get_price("sol", "T", "token_info")
    assert px1 == 1.0
    assert px2 == 2.0
    assert calls["n"] == 2
    await client.aclose()
