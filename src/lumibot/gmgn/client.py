from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
import urllib.error
import urllib.request
from collections import OrderedDict
from typing import Any
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

HOST = "https://openapi.gmgn.ai"
USER_AGENT = "gmgn-cli/1.5.4"


class RateLimiter:
    def __init__(self, capacity: float, refill_per_sec: float) -> None:
        self.capacity = capacity
        self.tokens = capacity
        self.refill_per_sec = refill_per_sec
        self.updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, cost: float = 1.0) -> None:
        while True:
            wait = 0.0
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.updated
                self.updated = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)
                if self.tokens >= cost:
                    self.tokens -= cost
                    return
                need = cost - self.tokens
                wait = need / self.refill_per_sec + 0.01
            await asyncio.sleep(wait)

    async def available(self) -> float:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.updated
            return min(self.capacity, self.tokens + elapsed * self.refill_per_sec)


class EnrichmentCache:
    """TTL cache with LRU eviction for token_info / token_security payloads.

    maxsize caps memory usage: when the cache is full, the least-recently-set
    entry is evicted first.  This prevents unbounded growth when scanning
    thousands of short-lived meme tokens over a long session.
    """

    def __init__(self, ttl_sec: int, maxsize: int = 5_000) -> None:
        self.ttl = ttl_sec
        self.maxsize = maxsize
        self._store: OrderedDict[tuple[str, str, str], tuple[float, Any]] = OrderedDict()

    def get(self, kind: str, chain: str, address: str) -> Any | None:
        key = (kind, chain, address)
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        # Move to end to record recent access (LRU)
        self._store.move_to_end(key)
        return value

    def set(self, kind: str, chain: str, address: str, value: Any) -> None:
        key = (kind, chain, address)
        self._store[key] = (time.time(), value)
        self._store.move_to_end(key)
        # Evict oldest entries when over capacity
        while len(self._store) > self.maxsize:
            self._store.popitem(last=False)

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns the number removed."""
        now = time.time()
        expired = [k for k, (ts, _) in self._store.items() if now - ts > self.ttl]
        for k in expired:
            self._store.pop(k, None)
        return len(expired)


class GmgnClient:
    """GMGN OpenAPI client.

    Uses stdlib urllib instead of httpx: Cloudflare currently challenges
    httpx's TLS fingerprint on this host, while urllib/curl succeed.
    """

    def __init__(
        self,
        api_key: str,
        rate_limiter: RateLimiter,
        cache_ttl_sec: int = 300,
        security_cache_ttl_sec: int | None = None,
        min_interval_sec: float = 1.0,
    ) -> None:
        self.api_key = api_key
        self.limiter = rate_limiter
        self.cache = EnrichmentCache(cache_ttl_sec)
        # token_security payloads (honeypot/renounced/tax) change far less often than
        # price/liquidity, so they get their own (longer-lived) cache by default.
        self.security_cache = EnrichmentCache(
            security_cache_ttl_sec if security_cache_ttl_sec is not None else cache_ttl_sec
        )
        # When GMGN bans the IP (429 + RATE_LIMIT_BANNED), fail fast without any
        # HTTP call until reset_at. Polling loops then stop re-triggering the ban.
        self._suspended_until: float = 0.0
        # GMGN OpenAPI default rate limit is 1 request/second; the token-bucket
        # limiter allows short bursts that still trip server-side 429s. This
        # global minimum interval serializes every request to the documented
        # default (configurable via global.rate_limit.min_interval_sec).
        self.min_interval_sec = min_interval_sec
        self._last_request_at = 0.0
        self._throttle_lock = asyncio.Lock()

    async def aclose(self) -> None:
        return None

    def _auth_query(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        q: dict[str, Any] = {
            "timestamp": int(time.time()),
            "client_id": str(uuid.uuid4()),
        }
        if extra:
            q.update(extra)
        return q

    def _sync_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
    ) -> tuple[int, dict[str, str], bytes]:
        data = None if body is None else json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return int(resp.status), hdrs, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            hdrs = {k.lower(): v for k, v in exc.headers.items()} if exc.headers else {}
            return int(exc.code), hdrs, raw

    async def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        weight: float = 1.0,
    ) -> Any:
        await self.limiter.acquire(weight)
        now = time.time()
        if now < self._suspended_until:
            # Fail fast without touching the network: a banned IP must not emit
            # further 429s, or the ban window keeps re-arming.
            raise RuntimeError(
                f"GMGN IP banned until {self._suspended_until:.0f}; "
                f"requests fail fast for {self._suspended_until - now:.0f}s"
            )
        async with self._throttle_lock:
            now = time.time()
            wait = self.min_interval_sec - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at = time.time()
        q = self._auth_query(query)
        url = f"{HOST}{path}?{urlencode(q, doseq=True)}"
        headers = {
            "X-APIKEY": self.api_key,
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(2):
            status, hdrs, raw = await asyncio.to_thread(self._sync_request, method, url, headers, body)
            text = raw.decode("utf-8", errors="replace")
            if status == 429:
                reset = hdrs.get("x-ratelimit-reset")
                body_json: dict[str, Any] = {}
                try:
                    body_json = json.loads(text) if text else {}
                except Exception:  # noqa: BLE001
                    pass
                reset_at = body_json.get("reset_at") or reset
                wait = 5.0
                if reset_at is not None:
                    try:
                        wait = max(1.0, float(reset_at) - time.time() + 1.0)
                    except (TypeError, ValueError):
                        wait = 5.0
                wait = min(wait, 60.0)
                logger.warning("GMGN 429 on %s %s, backoff %.1fs", method, path, wait)
                reset_ts: float | None = None
                if reset_at is not None:
                    try:
                        reset_ts = float(reset_at)
                    except (TypeError, ValueError):
                        reset_ts = None
                self._suspended_until = max(
                    self._suspended_until,
                    reset_ts if reset_ts is not None else time.time() + wait,
                )
                if attempt == 0 and wait <= 5.0:
                    await asyncio.sleep(wait)
                    await self.limiter.acquire(weight)
                    continue
                raise RuntimeError(f"GMGN rate limited on {method} {path}, retry after {wait:.0f}s")
            if status in (401, 403):
                raise RuntimeError(
                    f"GMGN {method} {path} HTTP {status}: {text[:500]}. "
                    "If this persists on dual-stack hosts, force IPv4 outbound "
                    "(GMGN is IPv4-only) or run on an IPv4 VPS."
                )
            if status >= 400:
                raise RuntimeError(f"GMGN {method} {path} HTTP {status}: {text[:500]}")
            try:
                data = json.loads(text) if text else {}
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"GMGN {method} {path} invalid JSON: {text[:200]}") from exc
            return _unwrap_envelope(data)
        raise RuntimeError(f"GMGN request failed {method} {path}")

    async def get_token_signal(self, chain: str, signal_types: list[int]) -> list[dict[str, Any]]:
        groups = [{"signal_type": signal_types}]
        data = await self._request(
            "POST",
            "/v1/market/token_signal",
            body={"chain": chain, "groups": groups},
            weight=3,
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in ("list", "signals", "items"):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    async def get_trending(self, chain: str, interval: str = "5m") -> list[dict[str, Any]]:
        data = await self._request(
            "GET",
            "/v1/market/rank",
            query={"chain": chain, "interval": interval},
            weight=1,
        )
        if isinstance(data, dict) and isinstance(data.get("rank"), list):
            return data["rank"]
        if isinstance(data, list):
            return data
        return []

    async def get_token_info(
        self, chain: str, address: str, *, use_cache: bool = True
    ) -> dict[str, Any]:
        if use_cache:
            cached = self.cache.get("info", chain, address)
            if cached is not None:
                return cached
        data = await self._request(
            "GET",
            "/v1/token/info",
            query={"chain": chain, "address": address},
            weight=1,
        )
        result = data if isinstance(data, dict) else {}
        self.cache.set("info", chain, address, result)
        return result

    async def get_token_security(self, chain: str, address: str) -> dict[str, Any]:
        cached = self.security_cache.get("security", chain, address)
        if cached is not None:
            return cached
        data = await self._request(
            "GET",
            "/v1/token/security",
            query={"chain": chain, "address": address},
            weight=1,
        )
        result = data if isinstance(data, dict) else {}
        self.security_cache.set("security", chain, address, result)
        return result

    async def get_price(self, chain: str, address: str, source: str = "token_info") -> float | None:
        price, _mc = await self.get_price_and_market_cap(chain, address, source)
        return price

    async def get_price_and_market_cap(
        self, chain: str, address: str, source: str = "token_info"
    ) -> tuple[float | None, float | None]:
        price, mc, _info = await self.get_fresh_snapshot(chain, address, source)
        return price, mc

    async def get_fresh_snapshot(
        self, chain: str, address: str, source: str = "token_info"
    ) -> tuple[float | None, float | None, dict[str, Any]]:
        """Uncached token_info + price/mc for post-gate open and push card."""
        info = await self.get_token_info(chain, address, use_cache=False)
        if not isinstance(info, dict):
            info = {}
        price = _price_from_info_dict(info)
        if source == "kline":
            kline_px = await self._price_from_kline(chain, address)
            if kline_px is not None:
                price = kline_px
        return price, _market_cap_from_info_dict(info), info

    async def _price_from_info(self, chain: str, address: str) -> float | None:
        info = await self.get_token_info(chain, address, use_cache=False)
        return _price_from_info_dict(info)

    async def _price_from_kline(self, chain: str, address: str) -> float | None:
        now = int(time.time())
        data = await self._request(
            "GET",
            "/v1/market/token_kline",
            query={
                "chain": chain,
                "address": address,
                "resolution": "1m",
                "from": now - 300,
                "to": now,
            },
            weight=2,
        )
        rows = data.get("list") if isinstance(data, dict) else None
        if isinstance(rows, list) and rows:
            last = rows[-1]
            return _as_float(last.get("close") or last.get("price"))
        return None


def _unwrap_envelope(data: Any) -> Any:
    """Unwrap nested `{code:0,data:...}` envelopes used by some GMGN routes."""
    cur = data
    for _ in range(3):
        if not isinstance(cur, dict):
            return cur
        code = cur.get("code")
        if code not in (None, 0, "0"):
            raise RuntimeError(f"GMGN API error {code}: {cur}")
        if "data" in cur and isinstance(cur["data"], (dict, list)):
            # Stop if this level already looks like a payload (has rank/list/etc).
            if any(k in cur for k in ("rank", "list", "signals", "items", "address")):
                return cur
            cur = cur["data"]
            continue
        return cur
    return cur


def _price_from_info_dict(info: dict[str, Any]) -> float | None:
    price_obj = info.get("price")
    if isinstance(price_obj, dict) and price_obj.get("price") is not None:
        return _as_float(price_obj.get("price"))
    if info.get("price") is not None and not isinstance(info.get("price"), dict):
        return _as_float(info.get("price"))
    return None


def _market_cap_from_info_dict(info: dict[str, Any]) -> float | None:
    for key in ("market_cap", "mc", "usd_market_cap"):
        v = _as_float(info.get(key))
        if v is not None and v > 0:
            return v
    price_obj = info.get("price")
    if isinstance(price_obj, dict):
        for key in ("market_cap", "mc", "usd_market_cap"):
            v = _as_float(price_obj.get(key))
            if v is not None and v > 0:
                return v
    # Newer token_info payloads often omit market_cap; derive from price × supply.
    price = _price_from_info_dict(info)
    if price is None or price <= 0:
        return None
    for key in ("circulating_supply", "total_supply"):
        supply = _as_float(info.get(key))
        if supply is not None and supply > 0:
            return price * supply
    return None


def _as_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
