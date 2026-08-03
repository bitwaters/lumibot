from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from lumibot.config import AppConfig, ChainCfg
from lumibot.db import Database
from lumibot.executors import Executor, LiveExecutor, PaperExecutor
from lumibot.filters import (
    apply_light_filters,
    apply_push_snapshot,
    evaluate_mc_extension,
    extract_platform,
    extract_signal_fields,
    extract_trending_fields,
    merge_info_fields,
    parse_open_timestamp,
)
from lumibot.gmgn.client import GmgnClient
from lumibot.models import Source, TokenCandidate
from lumibot.safety import evaluate_safety, normalize_security
from lumibot.telegram_notify import TelegramNotifier

logger = logging.getLogger(__name__)


class ChainPipeline:
    def __init__(
        self,
        chain: str,
        chain_cfg: ChainCfg,
        app_cfg: AppConfig,
        client: GmgnClient,
        db: Database,
        notifier: TelegramNotifier,
    ) -> None:
        self.chain = chain
        self.cfg = chain_cfg
        self.app_cfg = app_cfg
        self.client = client
        self.db = db
        self.notifier = notifier
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()
        self.executor: Executor
        if chain_cfg.execution.mode == "live":
            self.executor = LiveExecutor(db, app_cfg, chain, chain_cfg)
        else:
            self.executor = PaperExecutor(
                db,
                client,
                chain,
                chain_cfg,
                app_cfg.strategy,
                app_cfg.global_.price_source,
                notifier=notifier,
            )

    def start(self) -> None:
        if self.cfg.sources.signal.enabled:
            self._tasks.append(asyncio.create_task(self._loop_signal(), name=f"{self.chain}-signal"))
        if self.cfg.sources.trending.enabled:
            self._tasks.append(asyncio.create_task(self._loop_trending(), name=f"{self.chain}-trending"))
        if isinstance(self.executor, PaperExecutor):
            self._tasks.append(asyncio.create_task(self._loop_manage(), name=f"{self.chain}-manage"))

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _loop_signal(self) -> None:
        interval = self.cfg.sources.signal.interval_sec
        types = self.cfg.sources.signal.types
        while not self._stop.is_set():
            try:
                rows = await self.client.get_token_signal(self.chain, types)
                for raw in rows:
                    await self._handle_signal(raw)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("signal poll failed chain=%s", self.chain)
            await self._sleep(interval)

    async def _loop_trending(self) -> None:
        interval = self.cfg.sources.trending.interval_sec
        window = self.cfg.sources.trending.window
        while not self._stop.is_set():
            try:
                if await self.client.limiter.available() < 4:
                    logger.info("trending deferred chain=%s reason=rate_budget", self.chain)
                    await self._sleep(min(interval, 5))
                    continue
                rows = await self.client.get_trending(self.chain, window)
                for raw in rows:
                    await self._handle_trending(raw)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("trending poll failed chain=%s", self.chain)
            await self._sleep(interval)

    async def _loop_manage(self) -> None:
        assert isinstance(self.executor, PaperExecutor)
        while not self._stop.is_set():
            try:
                await self.executor.manage_open_positions()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("paper manage failed chain=%s", self.chain)
            await self._sleep(15)

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            return

    async def _handle_signal(self, raw: dict[str, Any]) -> None:
        seen_at = time.time()
        addr = raw.get("address") or raw.get("token_address") or dig_addr(raw)
        if not addr:
            return
        st = raw.get("signal_type") or raw.get("type")
        try:
            signal_type = int(st) if st is not None else None
        except (TypeError, ValueError):
            signal_type = None
        if signal_type is None or signal_type not in self.cfg.sources.signal.types:
            return
        fields = extract_signal_fields(raw)
        cand = TokenCandidate(
            chain=self.chain,
            address=str(addr),
            source=Source.SIGNAL,
            signal_type=signal_type,
            symbol=raw.get("symbol") or raw.get("token_symbol"),
            name=raw.get("name"),
            market_cap=fields["market_cap"],
            trigger_mc=fields["trigger_mc"],
            liquidity=fields["liquidity"],
            holder_count=fields["holder_count"],
            top10_rate=fields["top10_rate"],
            visiting_count=None,
            price=fields["price"],
            platform=extract_platform(raw),
            raw=raw,
            seen_at=seen_at,
            open_timestamp=parse_open_timestamp(raw),
        )
        await self._enrich_and_process(cand, need_visiting_from_info=True)

    async def _handle_trending(self, raw: dict[str, Any]) -> None:
        seen_at = time.time()
        addr = raw.get("address") or raw.get("token_address")
        if not addr:
            return
        fields = extract_trending_fields(raw)
        cand = TokenCandidate(
            chain=self.chain,
            address=str(addr),
            source=Source.TRENDING,
            symbol=raw.get("symbol") or raw.get("token_symbol"),
            name=raw.get("name"),
            market_cap=fields["market_cap"],
            liquidity=fields["liquidity"],
            holder_count=fields["holder_count"],
            top10_rate=fields["top10_rate"],
            visiting_count=fields["visiting_count"],
            price=fields["price"],
            platform=extract_platform(raw),
            raw=raw,
            seen_at=seen_at,
            open_timestamp=parse_open_timestamp(raw),
        )
        await self._enrich_and_process(cand, need_visiting_from_info=False)

    async def _fresh_quote(self, cand: TokenCandidate) -> tuple[float | None, float | None, dict]:
        price_source = self.app_cfg.global_.price_source
        last_err: Exception | None = None
        for attempt in range(2):
            try:
                price, mc, info = await self.client.get_fresh_snapshot(
                    cand.chain, cand.address, price_source
                )
                if price is not None and price > 0:
                    return price, mc, info if isinstance(info, dict) else {}
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning(
                    "post_gate_quote_failed chain=%s token=%s attempt=%s err=%s",
                    cand.chain,
                    cand.address,
                    attempt + 1,
                    exc,
                )
            if attempt == 0:
                await asyncio.sleep(0.25)
        if last_err is not None:
            logger.error(
                "post_gate_quote_exhausted chain=%s token=%s err=%s",
                cand.chain,
                cand.address,
                last_err,
            )
        return None, None, {}

    async def _enrich_and_process(self, cand: TokenCandidate, *, need_visiting_from_info: bool) -> None:
        needs_info = need_visiting_from_info or any(
            v is None
            for v in (cand.market_cap, cand.liquidity, cand.top10_rate, cand.holder_count, cand.price)
        )
        if needs_info:
            try:
                info = await self.client.get_token_info(cand.chain, cand.address)
                merge_info_fields(
                    cand,
                    info if isinstance(info, dict) else {},
                    force_visiting=need_visiting_from_info,
                )
            except Exception:  # noqa: BLE001
                logger.exception("token info failed chain=%s token=%s", cand.chain, cand.address)
                if need_visiting_from_info:
                    await self._reject(cand, "visiting_missing")
                    return

        if need_visiting_from_info and cand.visiting_count is None:
            await self._reject(cand, "visiting_missing")
            return

        fr = apply_light_filters(cand, self.cfg.filters, platforms=self.cfg.platforms)
        if not fr.ok:
            await self._reject(cand, fr.reason or "filter")
            return

        try:
            sec = await self.client.get_token_security(cand.chain, cand.address)
        except Exception:  # noqa: BLE001
            logger.exception("token security failed chain=%s token=%s", cand.chain, cand.address)
            await self._reject(cand, "safety_fetch")
            return
        safety = evaluate_safety(
            self.cfg.safety_profile,
            normalize_security(sec if isinstance(sec, dict) else {}),
            self.cfg.safety,
        )
        cand.safety = safety
        if safety.hard_fail:
            await self._reject(cand, safety.reason or "safety")
            return

        ext = evaluate_mc_extension(cand, self.cfg.filters)
        if ext.reject:
            await self._reject(cand, ext.reason or "mc_extension")
            return
        if ext.soft:
            await self.db.bump_reject(cand.chain, cand.source.value, ext.reason or "mc_extension_soft")

        block = await self.db.has_reentry_block(cand.chain, cand.address)
        if block == "loss":
            await self._reject(cand, "loss_cooldown")
            return
        if block == "post_close":
            await self._reject(cand, "post_close_cooldown")
            return

        acquired = await self.db.try_acquire_cooldown(
            cand.chain,
            cand.address,
            cand.source_key,
            self.cfg.cooldown.same_type_min,
            self.cfg.cooldown.cross_source_min,
        )
        if not acquired:
            await self._reject(cand, "cooldown")
            return

        block = await self.db.has_reentry_block(cand.chain, cand.address)
        if block is not None:
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            reason = "loss_cooldown" if block == "loss" else "post_close_cooldown"
            await self._reject(cand, reason)
            return

        price, mc, info = await self._fresh_quote(cand)
        if price is None or price <= 0:
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            await self._reject(cand, "no_price")
            return
        # Push card + open_mark share this uncached snapshot (not gate/enrich cache).
        apply_push_snapshot(cand, info, price=price, market_cap=mc)

        text_payload: dict[str, Any] = {
            "chain": cand.chain,
            "address": cand.address,
            "source": cand.source_key,
            "symbol": cand.symbol,
        }
        if cand.open_timestamp is not None:
            text_payload["open_timestamp"] = cand.open_timestamp

        exec_result = await self.executor.on_alert(cand)
        if exec_result.status == "no_price":
            # Defensive: pipeline already quoted; do not push a no-price card.
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            await self._reject(cand, "no_price")
            return
        send_ts = time.time()
        latency_sec = (send_ts - cand.seen_at) if cand.seen_at is not None else None
        text_payload["ts"] = send_ts
        if latency_sec is not None:
            text_payload["latency_ms"] = int(latency_sec * 1000)
        text_payload["exec_status"] = exec_result.status
        any_ok, all_ok = await self.notifier.send_candidate(
            cand, paper=exec_result, latency_sec=latency_sec
        )
        if not any_ok:
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            if exec_result.status == "opened" and exec_result.position_id is not None:
                await self.db.abort_paper_open(exec_result.position_id)
                logger.error(
                    "telegram_failed chain=%s token=%s source=%s; cooldown released; paper aborted id=%s",
                    cand.chain,
                    cand.address,
                    cand.source_key,
                    exec_result.position_id,
                )
            else:
                logger.error(
                    "telegram_failed chain=%s token=%s source=%s; cooldown released",
                    cand.chain,
                    cand.address,
                    cand.source_key,
                )
            return
        if not all_ok:
            logger.error(
                "telegram_partial chain=%s token=%s source=%s; cooldown kept",
                cand.chain,
                cand.address,
                cand.source_key,
            )

        await self.db.insert_alert(
            cand.chain, cand.address, cand.source_key, json.dumps(text_payload)
        )
        logger.info(
            "alert_sent chain=%s token=%s source=%s exec=%s all_tg=%s latency_ms=%s",
            cand.chain,
            cand.address,
            cand.source_key,
            exec_result.status,
            all_ok,
            text_payload.get("latency_ms"),
        )

    async def _reject(self, cand: TokenCandidate, reason: str) -> None:
        await self.db.bump_reject(cand.chain, cand.source.value, reason)
        logger.info(
            "reject chain=%s source=%s token=%s reason=%s",
            cand.chain,
            cand.source.value,
            cand.address,
            reason,
        )


def dig_addr(raw: dict[str, Any]) -> str | None:
    token = raw.get("token")
    if isinstance(token, dict):
        return token.get("address") or token.get("token_address")
    return None
