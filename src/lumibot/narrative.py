from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any

from lumibot.config import NarrativeCfg
from lumibot.models import TokenCandidate

logger = logging.getLogger(__name__)

NARRATIVE_MAX_LEN = 30
_NARRATIVE_NA = {"N/A", "NA", "无", "未知", ""}


class NarrativeClient:
    """Minimal OpenAI-compatible chat client for narrative inference (stdlib urllib)."""

    def __init__(self, api_key: str, cfg: NarrativeCfg) -> None:
        self.api_key = api_key
        self.cfg = cfg
        self.base_url = cfg.base_url.rstrip("/")

    async def complete(self, *, system: str, user: str) -> dict[str, Any]:
        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 128,
            "response_format": {"type": "json_object"},
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "lumibot-narrative/0.1",
            },
        )

        def _sync() -> Any:
            with urllib.request.urlopen(req, timeout=self.cfg.timeout_sec) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return json.loads(raw) if raw else {}

        return await asyncio.to_thread(_sync)


class NarrativeCache:
    """TTL cache of resolved narratives, keyed by (chain, address)."""

    def __init__(self, ttl_sec: int) -> None:
        self.ttl = ttl_sec
        self._store: dict[tuple[str, str], tuple[float, str]] = {}

    def get(self, chain: str, address: str) -> str | None:
        key = (chain, address)
        item = self._store.get(key)
        if not item:
            return None
        ts, value = item
        if time.time() - ts > self.ttl:
            self._store.pop(key, None)
            return None
        return value

    def set(self, chain: str, address: str, value: str) -> None:
        if not value:
            return
        self._store[(chain, address)] = (time.time(), value)

    def clear(self) -> None:
        self._store.clear()


SYSTEM_PROMPT = (
    "你是加密 meme 币分析助手。根据代币名称、简介和官网域名，"
    f"用不超过 {NARRATIVE_MAX_LEN} 个汉字的一句话描述它的叙事/主题"
    '（如"特朗普概念官方迷因币"、"AI Agent 概念"）。信息不足时输出 "N/A"。'
    '只输出 JSON: {"narrative": "..."}'
)


class NarrativeService:
    """LLM narrative inference with cache and guardrails. Pure display, no gating."""

    def __init__(self, api_key: str, cfg: NarrativeCfg) -> None:
        self.cfg = cfg
        self.client = NarrativeClient(api_key, cfg)
        self.cache = NarrativeCache(cfg.cache_ttl_sec)
        self._blocked = {s.lower() for s in cfg.symbol_blocklist}

    async def narrative_for(self, cand: TokenCandidate, info: dict[str, Any]) -> str | None:
        """Return a narrative sentence (<=30 chars) or None when unavailable."""
        if not self._eligible(cand):
            return None
        cached = self.cache.get(cand.chain, cand.address)
        if cached is not None:
            return cached
        try:
            text = await self._infer(cand, info)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "narrative_infer_failed chain=%s token=%s err=%s",
                cand.chain,
                cand.address,
                exc,
            )
            return None
        if text is None:
            return None
        self.cache.set(cand.chain, cand.address, text)
        return text

    def _eligible(self, cand: TokenCandidate) -> bool:
        sym = (cand.symbol or "").strip()
        if len(sym) < self.cfg.min_symbol_len:
            return False
        if sym.lower() in self._blocked:
            return False
        return True

    async def _infer(self, cand: TokenCandidate, info: dict[str, Any]) -> str | None:
        link = info.get("link") if isinstance(info.get("link"), dict) else {}
        desc = str(link.get("description") or "").strip()[:200]
        website = str(link.get("website") or "").strip()[:100]
        user = (
            f"symbol={cand.symbol} name={cand.name} "
            f"desc={desc} website={website}"
        )
        data = await self.client.complete(system=SYSTEM_PROMPT, user=user)
        narrative = self._extract(data)
        if narrative is None:
            return None
        return narrative[:NARRATIVE_MAX_LEN]

    @staticmethod
    def _extract(data: Any) -> str | None:
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        if isinstance(content, str):
            text = content.strip()
        else:
            text = str(content).strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                text = str(parsed.get("narrative") or "").strip()
        except (TypeError, ValueError):
            pass
        text = text.strip().strip("\"'")
        if text in _NARRATIVE_NA:
            return None
        return text or None
