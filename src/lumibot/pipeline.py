from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any

from lumibot.config import AppConfig, ChainCfg, SourceTrendingCfg
from lumibot.db import Database
from lumibot.executors import Executor, LiveExecutor, PaperExecutor
from lumibot.filters import (
    apply_light_filters,
    apply_push_snapshot,
    evaluate_chase,
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
        # Recent source sightings for dual-source (signal↔trending) within TTL.
        self._recent_sources: dict[str, dict[str, float]] = {}
        self._dual_source_ttl_sec = 30.0
        self.executor: Executor
        if chain_cfg.execution.mode == "live":
            self.executor = LiveExecutor(db, app_cfg, chain, chain_cfg)
        else:
            self.executor = PaperExecutor(
                db,
                client,
                chain,
                chain_cfg,
                chain_cfg.strategy,
                app_cfg.global_.price_source,
                notifier=notifier,
            )

    def start(self) -> None:
        if self.cfg.sources.signal.enabled:
            self._tasks.append(asyncio.create_task(self._loop_signal(), name=f"{self.chain}-signal"))
        if self.cfg.sources.trending.enabled:
            self._tasks.append(
                asyncio.create_task(
                    self._loop_trending(self.cfg.sources.trending), name=f"{self.chain}-trending"
                )
            )
        trending_5m = self.cfg.sources.trending_5m
        if trending_5m is not None and trending_5m.enabled:
            self._tasks.append(
                asyncio.create_task(
                    self._loop_trending(trending_5m), name=f"{self.chain}-trending-5m"
                )
            )
        if isinstance(self.executor, PaperExecutor):
            self._tasks.append(asyncio.create_task(self._loop_manage(), name=f"{self.chain}-manage"))

    async def stop(self) -> None:
        self._stop.set()
        tasks = list(self._tasks)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _loop_signal(self) -> None:
        interval = self.cfg.sources.signal.interval_sec
        types = self.cfg.sources.signal.types
        while not self._stop.is_set():
            try:
                rows = await self.client.get_token_signal(self.chain, types)
                for raw in rows:
                    try:
                        await self._handle_signal(raw)
                    except Exception:  # noqa: BLE001
                        logger.exception("signal row handling failed chain=%s", self.chain)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("signal poll failed chain=%s", self.chain)
            await self._sleep(interval)

    async def _loop_trending(self, cfg: SourceTrendingCfg) -> None:
        interval = cfg.interval_sec
        window = cfg.window
        while not self._stop.is_set():
            try:
                if await self.client.limiter.available() < 4:
                    logger.info("trending deferred chain=%s reason=rate_budget", self.chain)
                    await self._sleep(min(interval, 5))
                    continue
                rows = await self.client.get_trending(self.chain, window)
                for raw in rows:
                    try:
                        await self._handle_trending(raw)
                    except Exception:  # noqa: BLE001
                        logger.exception("trending row handling failed chain=%s", self.chain)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("trending poll failed chain=%s", self.chain)
            await self._sleep(interval)

    async def _loop_manage(self) -> None:
        assert isinstance(self.executor, PaperExecutor)
        # Randomise initial delay so multiple chains don't all fire at t=0
        await self._sleep(random.uniform(0, 5))
        while not self._stop.is_set():
            try:
                await self.executor.manage_open_positions()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("paper manage failed chain=%s", self.chain)
            # Add jitter to spread requests across chains
            await self._sleep(5 + random.uniform(0, 2))

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            return

    def _mark_dual_source(self, cand: TokenCandidate) -> None:
        """Record this sighting and set cand.dual_source if the other source hit recently."""
        now = time.time()
        ttl = self._dual_source_ttl_sec
        # Prune expired entries opportunistically
        stale_addrs = []
        for addr, bucket in self._recent_sources.items():
            alive = {src: ts for src, ts in bucket.items() if now - ts < ttl}
            if alive:
                self._recent_sources[addr] = alive
            else:
                stale_addrs.append(addr)
        for addr in stale_addrs:
            del self._recent_sources[addr]

        src = cand.source.value  # "signal" | "trending"
        other = "trending" if src == "signal" else "signal"
        bucket = self._recent_sources.setdefault(cand.address, {})
        other_ts = bucket.get(other)
        cand.dual_source = other_ts is not None and (now - other_ts) < ttl
        bucket[src] = now

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
            volume_1h=fields["volume_1h"],
            price=fields["price"],
            push_price=fields["price"],
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
            volume_1h=fields["volume_1h"],
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
        self._mark_dual_source(cand)

        # --- Fast-path DB checks BEFORE any API calls ---
        # This avoids burning rate-limit tokens on tokens already blocked by cooldown,
        # which happens every 5 s for the entire 45-min cooldown window.
        block = await self.db.has_reentry_block(cand.chain, cand.address)
        if block == "loss":
            await self._reject(cand, "loss_cooldown")
            return
        if block == "post_close":
            await self._reject(cand, "post_close_cooldown")
            return

        if cand.symbol and await self.db.has_symbol_block(cand.chain, cand.symbol):
            await self._reject(cand, "symbol_cooldown")
            return

        max_open = self.cfg.execution.limits.max_concurrent_positions
        if max_open > 0 and await self.db.count_open_papers(self.chain) >= max_open:
            # Reject without acquiring cooldown so a free slot can be used immediately.
            await self._reject(cand, "max_concurrent_positions")
            return

        cooldown_reason = await self.db.check_cooldown(
            cand.chain, cand.address, cand.source_key,
            self.cfg.cooldown.same_type_min,
            self.cfg.cooldown.cross_source_min,
        )
        if cooldown_reason is not None:
            await self._reject(cand, cooldown_reason)
            return

        # --- API enrichment (after cheap DB gates pass) ---
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

        # --- Atomic cooldown acquire + TOCTOU re-check ---
        cooldown_reason = await self.db.try_acquire_cooldown(
            cand.chain,
            cand.address,
            cand.source_key,
            self.cfg.cooldown.same_type_min,
            self.cfg.cooldown.cross_source_min,
        )
        if cooldown_reason is not None:
            await self._reject(cand, cooldown_reason)
            return

        block = await self.db.has_reentry_block(cand.chain, cand.address)
        if block is not None:
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            reason = "loss_cooldown" if block == "loss" else "post_close_cooldown"
            await self._reject(cand, reason)
            return

        # Second symbol check: symbol may only be known after enrichment.
        if cand.symbol and await self.db.has_symbol_block(cand.chain, cand.symbol):
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            await self._reject(cand, "symbol_cooldown")
            return

        price, mc, info = await self._fresh_quote(cand)
        if price is None or price <= 0:
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            await self._reject(cand, "no_price")
            return
        # Chase gate: if the fresh quote already ran well past the push payload
        # price, the signal arrived late and opening here buys the top.
        if evaluate_chase(cand, price, self.cfg.filters):
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            await self._reject(cand, "chase")
            return
        # Push card + open_mark share this uncached snapshot (not gate/enrich cache).
        apply_push_snapshot(cand, info, price=price, market_cap=mc)
        send_ts = time.time()
        latency_sec = (send_ts - cand.seen_at) if cand.seen_at is not None else None

        open_paper = await self.db.get_open_paper(cand.chain, cand.address)
        if open_paper is not None:
            text_payload = {
                "chain": cand.chain,
                "address": cand.address,
                "source": cand.source_key,
                "symbol": cand.symbol,
                "dual_source": cand.dual_source,
                "exec_status": "skipped_open",
                "ts": send_ts,
            }
            text_payload.update(self._payload_features(cand))
            if cand.open_timestamp is not None:
                text_payload["open_timestamp"] = cand.open_timestamp
            if latency_sec is not None:
                text_payload["latency_ms"] = int(latency_sec * 1000)

            any_ok, _all_ok, sent_message_ids = await self.notifier.send_candidate(
                cand,
                latency_sec=latency_sec,
                paper_status="precheck_skipped_open",
            )
            if not any_ok:
                await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
                logger.error(
                    "telegram_failed chain=%s token=%s source=%s; cooldown released",
                    cand.chain,
                    cand.address,
                    cand.source_key,
                )
                return
            await self.db.insert_alert(
                cand.chain, cand.address, cand.source_key, json.dumps(text_payload)
            )
            return

        text_payload: dict[str, Any] = {
            "chain": cand.chain,
            "address": cand.address,
            "source": cand.source_key,
            "symbol": cand.symbol,
            "dual_source": cand.dual_source,
            "ts": send_ts,
        }
        text_payload.update(self._payload_features(cand))
        if cand.open_timestamp is not None:
            text_payload["open_timestamp"] = cand.open_timestamp
        if latency_sec is not None:
            text_payload["latency_ms"] = int(latency_sec * 1000)
        text_payload["exec_status"] = "opening"
        any_ok, _all_ok, sent_message_ids = await self.notifier.send_candidate(
            cand,
            latency_sec=latency_sec,
            paper_status="opening",
        )
        if not any_ok:
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            logger.error(
                "telegram_failed chain=%s token=%s source=%s; cooldown released",
                cand.chain,
                cand.address,
                cand.source_key,
            )
            return

        try:
            exec_result = await self.executor.on_alert(cand)
        except Exception:  # noqa: BLE001
            logger.exception(
                "executor_on_alert_failed chain=%s token=%s", cand.chain, cand.address
            )
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            await self._reject(cand, "executor_error")
            try:
                await self.notifier.edit_candidate(
                    cand,
                    latency_sec=latency_sec,
                    message_ids=sent_message_ids,
                    paper_status="executor_error",
                )
            except Exception:  # noqa: BLE001
                logger.warning(
                    "executor_error_edit_failed chain=%s token=%s",
                    cand.chain,
                    cand.address,
                )
            return
        text_payload["exec_status"] = exec_result.status
        any_ok, all_ok = await self.notifier.edit_candidate(
            cand,
            paper=exec_result,
            latency_sec=latency_sec,
            message_ids=sent_message_ids,
        )
        if not any_ok:
            logger.error(
                "telegram_update_failed chain=%s token=%s source=%s; card remains opening",
                cand.chain,
                cand.address,
                cand.source_key,
            )

        if exec_result.status == "no_price":
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            await self._reject(cand, "no_price")
            return

        if exec_result.status == "blocked_max_positions":
            # Race: slot filled between early check and open. Free cooldown so a
            # later free slot can be used; still keep a final card so operators see the cap hit.
            await self.db.release_cooldown(cand.chain, cand.address, cand.source_key)
            if not all_ok:
                logger.error(
                    "telegram_partial chain=%s token=%s source=%s; cooldown released",
                    cand.chain,
                    cand.address,
                    cand.source_key,
                )

        if not all_ok:
            if exec_result.status != "blocked_max_positions":
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

    @staticmethod
    def _payload_features(cand: TokenCandidate) -> dict[str, Any]:
        """Filter/quote features at push time, for offline calibration later."""
        out: dict[str, Any] = {
            "market_cap": cand.market_cap,
            "liquidity": cand.liquidity,
            "top10_rate": cand.top10_rate,
            "holder_count": cand.holder_count,
            "visiting_count": cand.visiting_count,
            "volume_1h": cand.volume_1h,
        }
        if cand.price is not None:
            out["price"] = cand.price
        if cand.push_price is not None:
            out["push_price"] = cand.push_price
        if cand.open_timestamp is not None:
            out["age_sec"] = max(0.0, time.time() - cand.open_timestamp)
        return out

    async def _reject(self, cand: TokenCandidate, reason: str) -> None:
        await self.db.bump_reject(cand.chain, cand.source.value, reason)
        try:
            payload = json.dumps(
                {
                    "symbol": cand.symbol,
                    "source_key": cand.source_key,
                    "dual_source": cand.dual_source,
                    "market_cap": cand.market_cap,
                    "platform": cand.platform,
                },
                ensure_ascii=False,
            )
            await self.db.insert_signal_log(
                cand.chain, cand.address, cand.source.value, reason, payload
            )
        except Exception:  # noqa: BLE001
            logger.exception(
                "signal_log_failed chain=%s token=%s reason=%s",
                cand.chain,
                cand.address,
                reason,
            )
        logger.info(
            "reject chain=%s source=%s token=%s reason=%s dual=%s",
            cand.chain,
            cand.source.value,
            cand.address,
            reason,
            cand.dual_source,
        )

def dig_addr(raw: dict[str, Any]) -> str | None:
    token = raw.get("token")
    if isinstance(token, dict):
        return token.get("address") or token.get("token_address")
    return None
