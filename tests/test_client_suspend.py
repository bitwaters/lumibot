import time

import pytest

from lumibot.gmgn.client import GmgnClient, RateLimiter


@pytest.mark.asyncio
async def test_429_suspends_requests_until_reset(monkeypatch):
    client = GmgnClient("k", RateLimiter(10, 10), cache_ttl_sec=300)
    calls = {"n": 0}

    def fake_sync(method, url, headers, body):
        calls["n"] += 1
        return 429, {"x-ratelimit-reset": str(int(time.time()) + 300)}, b'{"reset_at": %d}' % (
            int(time.time()) + 300,
        )

    monkeypatch.setattr(client, "_sync_request", fake_sync)

    with pytest.raises(RuntimeError, match="retry after"):
        await client._request("GET", "/v1/market/rank")
    assert calls["n"] == 1
    assert client._suspended_until > time.time() + 250

    # While suspended: fail fast, no HTTP call at all.
    with pytest.raises(RuntimeError, match="fail fast"):
        await client._request("GET", "/v1/market/rank")
    assert calls["n"] == 1

    # After the suspension window passes, requests go out again.
    client._suspended_until = time.time() - 1
    calls2 = {"n": 0}
    monkeypatch.setattr(client, "_sync_request", lambda *a, **k: (200, {}, b'{"ok": true}'))
    data = await client._request("GET", "/v1/market/rank")
    assert data == {"ok": True}
    await client.aclose()


@pytest.mark.asyncio
async def test_429_without_reset_uses_default_suspension(monkeypatch):
    client = GmgnClient("k", RateLimiter(10, 10), cache_ttl_sec=300)
    monkeypatch.setattr(client, "_sync_request", lambda *a, **k: (429, {}, b"{}"))
    with pytest.raises(RuntimeError, match="retry after"):
        await client._request("GET", "/v1/market/rank")
    assert client._suspended_until > time.time() + 4
    await client.aclose()
