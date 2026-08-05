from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from lumibot.config import NewsCfg
from lumibot.models import TokenCandidate

logger = logging.getLogger(__name__)


HOST = "https://ai.6551.io"


_DEFAULT_ENDPOINTS = [
    "/api/search",
    "/v1/search",
    "/search",
]


@dataclass(frozen=True)
class NewsHit:
    title: str
    summary: str
    score: float
    source: str = "OpenNews"

    def news_line(self, *, label: str) -> str:
        text = self.title.strip()
        if self.summary:
            text = self.summary.strip()
            if len(text) > 180:
                text = f"{text[:177]}…"
        if not text:
            text = self.title.strip()
        if len(text) > 180:
            text = f"{text[:177]}…"
        return f"📰 {label} {text}"


class NewsCache:
    """TTL cache for resolved OpenNews payloads, keyed by normalized query."""

    def __init__(self, ttl_sec: int = 60) -> None:
        self.ttl = ttl_sec
        self._store: dict[str, tuple[float, list[NewsHit]]] = {}

    def get(self, query: str) -> list[NewsHit] | None:
        key = query.lower().strip()
        if not key:
            return None
        item = self._store.get(key)
        if not item:
            return None
        ts, hits = item
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return hits

    def set(self, query: str, hits: list[NewsHit]) -> None:
        key = query.lower().strip()
        if not key:
            return
        self._store[key] = (time.time(), hits)

    def clear(self) -> None:
        self._store.clear()


class OpenNewsClient:
    def __init__(self, token: str, *, host: str = HOST, timeout_sec: int = 20) -> None:
        self.token = token
        self.host = host.rstrip("/")
        self.timeout_sec = timeout_sec

    async def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        if not query:
            return []
        for endpoint in _DEFAULT_ENDPOINTS:
            try:
                data = await self._request("GET", endpoint, {"q": query, "limit": limit})
                items = self._extract_items(data)
                if items:
                    return items
            except Exception as exc:  # noqa: BLE001
                logger.warning("opennews endpoint failed endpoint=%s query=%s err=%s", endpoint, query, exc)
        return []

    def _extract_items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            raw = payload
        elif isinstance(payload, dict):
            for key in ("items", "data", "news", "results"):
                value = payload.get(key)
                if isinstance(value, list):
                    raw = value
                    break
            else:
                # Some MCP-like payloads wrap list inside {"data":{"items":[...]}}
                for wrapper in ("data",):
                    value = payload.get(wrapper)
                    if isinstance(value, dict):
                        for key in ("items", "news", "results"):
                            wrapped = value.get(key)
                            if isinstance(wrapped, list):
                                raw = wrapped
                                break
                        else:
                            continue
                        break
                else:
                    raw = []
        else:
            raw = []
        return [self._normalize_item(item) for item in raw if isinstance(item, dict)]

    def _normalize_item(self, item: dict[str, Any]) -> dict[str, Any]:
        title = str(item.get("title", "")).strip()
        summary = str(item.get("summary", item.get("content", item.get("desc", "")))).strip()
        score = float(item.get("score", item.get("ai_score", 0.0)) or 0.0)
        source = str(item.get("source", "opennews"))
        return {"title": title, "summary": summary, "score": score, "source": source}

    async def _request(self, method: str, path: str, query: dict[str, Any] | None = None) -> Any:
        q = urlencode(query or {}, doseq=True)
        url = f"{self.host}{path}"
        if q:
            url = f"{url}?{q}"

        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-API-KEY": self.token,
            "User-Agent": "lumibot-news/0.1",
            "Accept": "application/json",
        }

        def _sync() -> Any:
            req = urllib.request.Request(url, method=method, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}

        status_payload = await asyncio.to_thread(_sync)
        return status_payload


class NewsPoller:
    def __init__(self, client: OpenNewsClient, cfg: NewsCfg) -> None:
        self.client = client
        self.cfg = cfg
        self.cache = NewsCache(ttl_sec=max(30, cfg.lookback_min * 60))
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="opennews-poller")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            await self._refresh_markets()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(10, self.cfg.poll_sec))
            except asyncio.TimeoutError:
                continue

    async def _refresh_markets(self) -> None:
        if not self.cfg.enabled or not self.cfg.market_coins or not self.cfg.market_keywords:
            return
        for coin in self.cfg.market_coins:
            for keyword in self.cfg.market_keywords:
                q = f"{coin} {keyword}".strip()
                hits = await self._search_cached(q, allow_net=True)
                if hits:
                    self.cache.set(q, hits)

    async def _search_cached(self, query: str, *, allow_net: bool) -> list[NewsHit]:
        cached = self.cache.get(query)
        if cached is not None:
            return cached
        if not allow_net:
            return []
        try:
            items = await self.client.search(query)
        except Exception as exc:  # noqa: BLE001
            logger.warning("opennews search failed query=%s err=%s", query, exc)
            items = []
        hits: list[NewsHit] = []
        for item in items:
            title = str(item.get("title", "")).strip()
            if not title:
                continue
            score = float(item.get("score", 0.0) or 0.0)
            hits.append(
                NewsHit(
                    title=title,
                    summary=str(item.get("summary", "")).strip(),
                    score=score,
                    source=str(item.get("source", "opennews")),
                )
            )
        hits.sort(key=lambda hit: hit.score, reverse=True)
        self.cache.set(query, hits)
        return hits

    async def match_news(self, cand: TokenCandidate) -> str | None:
        if not self.cfg.enabled:
            return None

        # 1) Token-level first: symbol/name.
        symbol = (cand.symbol or "").strip()
        name = (cand.name or "").strip()
        symbol_blocked = {s.lower() for s in self.cfg.symbol_blocklist}
        if symbol and symbol.lower() not in symbol_blocked and len(symbol) >= self.cfg.min_symbol_len:
            q = f"{symbol} {name}".strip()
            hits = await self._search_cached(q, allow_net=True)
            if hits:
                selected = hits[0]
                if selected.score >= self.cfg.min_score:
                    return selected.news_line(label="相关")

        # 2) Market fallback only when token-level did not hit.
        for coin in self.cfg.market_coins:
            for keyword in self.cfg.market_keywords or ["meme"]:
                q = f"{coin} {keyword}".strip()
                hits = await self._search_cached(q, allow_net=False)
                if not hits:
                    continue
                selected = hits[0]
                if selected.score >= self.cfg.min_score:
                    return selected.news_line(label="市场")
        return None
