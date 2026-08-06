from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from lumibot.config import AppConfig, ChainCfg, StrategyCfg
from lumibot.db import Database
from lumibot.exec_types import ExecResult, PaperTradeEvent
from lumibot.gmgn.client import GmgnClient
from lumibot.models import TokenCandidate
from lumibot.strategy import Action, StrategyOrder
from lumibot.util import mc_from_price_ratio

if TYPE_CHECKING:
    from lumibot.telegram_notify import TelegramNotifier

logger = logging.getLogger(__name__)


class Executor(ABC):
    @abstractmethod
    async def on_alert(self, cand: TokenCandidate) -> ExecResult:
        """Process alert and return open result for the card."""


class PaperExecutor(Executor):
    def __init__(
        self,
        db: Database,
        client: GmgnClient,
        chain: str,
        chain_cfg: ChainCfg,
        strategy: StrategyCfg,
        price_source: str,
        notifier: TelegramNotifier | None = None,
    ) -> None:
        self.db = db
        self.client = client
        self.chain = chain
        self.chain_cfg = chain_cfg
        self.strategy = strategy
        self.price_source = price_source
        self.notifier = notifier

    async def on_alert(self, cand: TokenCandidate) -> ExecResult:
        # Pipeline must supply a post-gate fresh quote on cand.price.
        mark = cand.price
        if mark is None or mark <= 0:
            logger.warning("paper open skipped: no price chain=%s token=%s", cand.chain, cand.address)
            return ExecResult(status="no_price")

        max_open = self.chain_cfg.execution.limits.max_concurrent_positions
        order = StrategyOrder.open_from_mark(
            chain=cand.chain,
            token=cand.address,
            mark=mark,
            notional_usd=self.strategy.notional_usd,
            buy_slip=self.chain_cfg.execution.slippage_buy_pct,
            sell_slip=self.chain_cfg.execution.slippage_sell_pct,
            opened_at=time.time(),
            hard_stop_pct=self.strategy.hard_stop_pct,
            stage1_tp_pct=self.strategy.stage1_tp_pct,
            trail_drawdown_pct=self.strategy.trail_drawdown_pct,
            timeout_hours=self.strategy.timeout_hours,
            stage1_sell_mode=self.strategy.stage1_sell_mode,
            stage1_sell_ratio=self.strategy.stage1_sell_ratio,
            pre_stage1_trail_enable=self.strategy.pre_stage1_trail_enable,
            pre_stage1_trail_activate_pct=self.strategy.pre_stage1_trail_activate_pct,
            pre_stage1_trail_drawdown_pct=self.strategy.pre_stage1_trail_drawdown_pct,
            timeout_extend_if_profitable=self.strategy.timeout_extend_if_profitable,
            timeout_extend_hours=self.strategy.timeout_extend_hours,
            trail_dynamic=self.strategy.trail_dynamic,
            early_stop_pct=self.strategy.early_stop_pct,
            early_stop_sec=self.strategy.early_stop_sec,
            momentum_sec=self.strategy.momentum_sec,
            momentum_activate_pct=self.strategy.momentum_activate_pct,
            momentum_exit_pct=self.strategy.momentum_exit_pct,
        )
        pos_id, skip_reason = await self.db.try_open_paper(
            cand.chain,
            cand.address,
            order.entry_price,
            order.qty,
            order.notional_usd,
            order.peak_price,
            symbol=cand.symbol,
            open_mark=order.open_mark,
            max_concurrent=max_open,
        )
        if skip_reason == "max_concurrent":
            logger.info(
                "paper_skip_open chain=%s token=%s reason=max_concurrent_positions max=%s",
                cand.chain,
                cand.address,
                max_open,
            )
            return ExecResult(
                status="blocked_max_positions",
                mark=mark,
                open_mark=mark,
                hard_stop_pct=self.strategy.hard_stop_pct,
            )
        if skip_reason == "already_open" or pos_id is None:
            logger.info(
                "paper_skip_open chain=%s token=%s reason=already_open",
                cand.chain,
                cand.address,
            )
            return ExecResult(
                status="skipped_open",
                mark=mark,
                open_mark=mark,
                hard_stop_pct=self.strategy.hard_stop_pct,
            )
        logger.info(
            "paper_opened chain=%s token=%s id=%s entry=%.8f open_mark=%.8f peak=%.8f",
            cand.chain,
            cand.address,
            pos_id,
            order.entry_price,
            order.open_mark,
            order.peak_price,
        )
        return ExecResult(
            status="opened",
            entry_price=order.entry_price,
            notional_usd=order.notional_usd,
            qty=order.qty,
            mark=mark,
            open_mark=order.open_mark,
            position_id=pos_id,
            buy_slip=order.buy_slip,
            hard_stop_pct=order.hard_stop_pct,
        )

    async def manage_open_positions(self) -> None:
        now = time.time()
        for row in await self.db.list_open_papers(self.chain):
            await self._manage_one(row, now)

        offsets = self.strategy.snapshots_sec
        for row in await self.db.list_snapshot_targets(self.chain, len(offsets)):
            if row["status"] == "open":
                continue
            due_missing = await self._due_missing_offsets(row, now)
            if not due_missing:
                continue
            mark = await self.client.get_price(row["chain"], row["token"], self.price_source)
            if mark is None or mark <= 0:
                continue
            await self._write_snapshots(int(row["id"]), due_missing, mark, closed=True)

    async def _manage_one(self, row, now: float) -> None:
        # Fetch price + market_cap in one call; reuse for both strategy evaluation
        # and exit-MC card fields, avoiding a redundant uncached API request on close.
        try:
            mark, mark_mc = await self.client.get_price_and_market_cap(
                row["chain"], row["token"], self.price_source
            )
        except Exception:  # noqa: BLE001
            logger.exception("manage_one quote failed chain=%s token=%s", row["chain"], row["token"])
            return
        if mark is None or mark <= 0:
            return
        keys = row.keys()
        open_mark = float(row["open_mark"]) if "open_mark" in keys and row["open_mark"] is not None else float(row["entry_price"])
        order = StrategyOrder(
            chain=row["chain"],
            token=row["token"],
            entry_price=row["entry_price"],
            open_mark=open_mark,
            notional_usd=row["notional_usd"],
            qty=row["qty"],
            cost_basis=row["cost_basis"],
            peak_price=row["peak_price"],
            stage1_done=bool(row["stage1_done"]),
            opened_at=row["opened_at"],
            buy_slip=self.chain_cfg.execution.slippage_buy_pct,
            sell_slip=self.chain_cfg.execution.slippage_sell_pct,
            hard_stop_pct=self.strategy.hard_stop_pct,
            stage1_tp_pct=self.strategy.stage1_tp_pct,
            trail_drawdown_pct=self.strategy.trail_drawdown_pct,
            timeout_hours=self.strategy.timeout_hours,
            stage1_sell_mode=self.strategy.stage1_sell_mode,
            stage1_sell_ratio=self.strategy.stage1_sell_ratio,
            pre_stage1_trail_enable=self.strategy.pre_stage1_trail_enable,
            pre_stage1_trail_activate_pct=self.strategy.pre_stage1_trail_activate_pct,
            pre_stage1_trail_drawdown_pct=self.strategy.pre_stage1_trail_drawdown_pct,
            timeout_extend_if_profitable=self.strategy.timeout_extend_if_profitable,
            timeout_extend_hours=self.strategy.timeout_extend_hours,
            trail_dynamic=self.strategy.trail_dynamic,
            early_stop_pct=self.strategy.early_stop_pct,
            early_stop_sec=self.strategy.early_stop_sec,
            momentum_sec=self.strategy.momentum_sec,
            momentum_activate_pct=self.strategy.momentum_activate_pct,
            momentum_exit_pct=self.strategy.momentum_exit_pct,
        )
        action, reason, sell_qty = order.evaluate(mark, now)
        if order.peak_price != row["peak_price"]:
            await self.db.update_paper_mark(row["id"], peak_price=order.peak_price)

        closed = False
        if action == Action.STAGE1_SELL:
            sell_px = StrategyOrder.sell_fill_price(mark, order.sell_slip)
            pnl = order.apply_stage1(mark, sell_qty)
            sold = await self.db.add_partial_sell(
                row["id"],
                sell_px,
                sell_qty,
                sell_qty * sell_px,
                order.qty,
                order.cost_basis,
                pnl,
            )
            if not sold:
                return
            logger.info(
                "paper_stage1 chain=%s token=%s reason=%s pnl=%.4f",
                row["chain"],
                row["token"],
                reason,
                pnl,
            )
            entry_mc, exit_mc, peak_mc = await self._exit_mc_fields(
                row["chain"],
                row["token"],
                open_mark,
                float(order.peak_price),
                fill_mark=mark,
                prefetch=(mark, mark_mc),
            )
            await self._notify_event(
                PaperTradeEvent(
                    kind="stage1",
                    chain=row["chain"],
                    token=row["token"],
                    symbol=row["symbol"] if "symbol" in keys else None,
                    reason=reason or "stage1",
                    mark=mark,
                    fill_price=sell_px,
                    qty=sell_qty,
                    pnl=pnl,
                    notional_usd=row["notional_usd"],
                    entry_price=row["entry_price"],
                    remaining_qty=order.qty,
                    open_mark=open_mark,
                    entry_mc=entry_mc,
                    exit_mc=exit_mc,
                    peak_mc=peak_mc,
                    hold_sec=now - float(row["opened_at"]),
                    sell_mode=order.stage1_sell_mode,
                )
            )
        elif action == Action.CLOSE:
            sell_px = StrategyOrder.sell_fill_price(mark, order.sell_slip)
            pnl = order.apply_close(mark, sell_qty)
            closed_ok = await self.db.close_paper(
                row["id"],
                sell_px,
                sell_qty,
                sell_qty * sell_px,
                reason or "close",
                pnl,
                loss_cooldown_min=self.strategy.loss_cooldown_min,
                post_close_cooldown_min=self.strategy.post_close_cooldown_min,
                symbol_cooldown_min=self.strategy.symbol_cooldown_min,
            )
            if not closed_ok:
                return
            logger.info(
                "paper_closed chain=%s token=%s reason=%s pnl=%.4f",
                row["chain"],
                row["token"],
                reason,
                pnl,
            )
            closed = True
            entry_mc, exit_mc, peak_mc = await self._exit_mc_fields(
                row["chain"],
                row["token"],
                open_mark,
                float(order.peak_price),
                fill_mark=mark,
                prefetch=(mark, mark_mc),
            )
            await self._notify_event(
                PaperTradeEvent(
                    kind="close",
                    chain=row["chain"],
                    token=row["token"],
                    symbol=row["symbol"] if "symbol" in keys else None,
                    reason=reason or "close",
                    mark=mark,
                    fill_price=sell_px,
                    qty=sell_qty,
                    pnl=pnl,
                    notional_usd=row["notional_usd"],
                    entry_price=row["entry_price"],
                    open_mark=open_mark,
                    entry_mc=entry_mc,
                    exit_mc=exit_mc,
                    peak_mc=peak_mc,
                    hold_sec=now - float(row["opened_at"]),
                )
            )

        due_missing = await self._due_missing_offsets(row, now)
        if due_missing:
            await self._write_snapshots(int(row["id"]), due_missing, mark, closed=closed)

    async def _exit_mc_fields(
        self,
        chain: str,
        token: str,
        open_mark: float,
        peak_price: float,
        *,
        fill_mark: float,
        prefetch: tuple[float | None, float | None] | None = None,
    ) -> tuple[float | None, float | None, float | None]:
        """Display MC after fills. Scale entry/peak/exit off one quote snapshot using fill_mark for exit.

        If prefetch=(quote_px, mark_mc) is provided (e.g. from _manage_one's opening quote),
        it is reused directly to avoid a second uncached API call within the same management tick.
        """
        if prefetch is not None:
            quote_px, mark_mc = prefetch
        else:
            try:
                quote_px, mark_mc = await self.client.get_price_and_market_cap(
                    chain, token, self.price_source
                )
            except Exception:  # noqa: BLE001
                logger.exception("exit quote failed chain=%s token=%s", chain, token)
                return None, None, None
        entry_mc = mc_from_price_ratio(mark_mc, quote_px, open_mark)
        peak_mc = mc_from_price_ratio(mark_mc, quote_px, peak_price)
        exit_mc = mc_from_price_ratio(mark_mc, quote_px, fill_mark)
        return entry_mc, exit_mc, peak_mc

    async def _notify_event(self, ev: PaperTradeEvent) -> None:
        if not self.notifier:
            return
        try:
            await self.notifier.send_paper_event(ev)
        except Exception:  # noqa: BLE001
            logger.exception("paper event notify failed token=%s", ev.token)

    async def _due_missing_offsets(self, row, now: float) -> list[int]:
        missing = await self.db.missing_snapshot_offsets(row["id"], self.strategy.snapshots_sec)
        return [o for o in missing if now >= row["opened_at"] + o]

    async def _write_snapshots(
        self, position_id: int, offsets: list[int], mark: float, *, closed: bool
    ) -> None:
        for offset in offsets:
            await self.db.insert_snapshot(position_id, offset, mark, closed)


class LiveExecutor(Executor):
    """Live trading stub — intentionally non-functional (U1 / Paper-first).

    Never submits real orders, never loads private keys or wallet material, and
    has no manage_open_positions loop. Enabling ``execution.mode: live`` only
    runs risk-limit checks then returns ``noop`` / ``blocked_live``. Real DEX
    routing (Jupiter/Raydium/etc.) is out of scope until a dedicated Live change.
    """

    def __init__(self, db: Database, app_cfg: AppConfig, chain: str, chain_cfg: ChainCfg) -> None:
        self.db = db
        self.app_cfg = app_cfg
        self.chain = chain
        self.chain_cfg = chain_cfg

    def _live_allowed(self) -> tuple[bool, str]:
        if not self.app_cfg.global_.live_master_switch:
            return False, "master_off"
        if not self.chain_cfg.execution.live_enabled:
            return False, "chain_live_off"
        return True, "ok"

    async def on_alert(self, cand: TokenCandidate) -> ExecResult:
        ok, reason = self._live_allowed()
        if not ok:
            logger.info("live_blocked chain=%s reason=%s", self.chain, reason)
            return ExecResult(status="blocked_live")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        stats = await self.db.get_live_daily(self.chain, day)
        limits = self.chain_cfg.execution.limits
        if stats:
            if float(stats["live_realized_pnl"]) <= -abs(limits.daily_loss_usd):
                logger.info("live_blocked chain=%s reason=daily_loss", self.chain)
                return ExecResult(status="blocked_live")
            if int(stats["live_trades"]) >= limits.daily_trades:
                logger.info("live_blocked chain=%s reason=daily_trades", self.chain)
                return ExecResult(status="blocked_live")
        logger.warning(
            "live_stub_noop chain=%s token=%s (P0 does not place real orders)",
            cand.chain,
            cand.address,
        )
        return ExecResult(status="noop")
