from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Action(str, Enum):
    HOLD = "hold"
    STAGE1_SELL = "stage1_sell"
    CLOSE = "close"


@dataclass
class StrategyOrder:
    chain: str
    token: str
    entry_price: float  # buy fill (with buy slip); cost/qty basis
    open_mark: float  # mark at open; hard stop reference
    notional_usd: float
    qty: float
    cost_basis: float
    peak_price: float
    stage1_done: bool
    opened_at: float
    buy_slip: float
    sell_slip: float
    hard_stop_pct: float = -0.30
    stage1_tp_pct: float = 0.25
    trail_drawdown_pct: float = 0.30
    timeout_hours: float = 2.0
    stage1_sell_mode: str = "notional"  # notional | ratio
    stage1_sell_ratio: float = 0.50     # used when stage1_sell_mode == "ratio"
    pre_stage1_trail_enable: bool = False
    pre_stage1_trail_activate_pct: float = 0.15
    pre_stage1_trail_drawdown_pct: float = 0.40
    timeout_extend_if_profitable: bool = False
    timeout_extend_hours: float = 1.0
    trail_dynamic: bool = True
    # Entry protection: tighter stop (relative to open_mark) for the first
    # early_stop_sec seconds; 0 disables.
    early_stop_pct: float = 0.0
    early_stop_sec: int = 0
    # No-momentum exit: close within momentum_sec if the price never rose
    # momentum_activate_pct above open_mark and now trades at/below
    # momentum_exit_pct; 0 disables.
    momentum_sec: int = 0
    momentum_activate_pct: float = 0.0
    momentum_exit_pct: float = 0.0

    @staticmethod
    def buy_fill_price(mark: float, buy_slip: float) -> float:
        return mark * (1.0 + buy_slip)

    @staticmethod
    def sell_fill_price(mark: float, sell_slip: float) -> float:
        return mark * (1.0 - sell_slip)

    @classmethod
    def open_from_mark(
        cls,
        *,
        chain: str,
        token: str,
        mark: float,
        notional_usd: float,
        buy_slip: float,
        sell_slip: float,
        opened_at: float,
        hard_stop_pct: float = -0.30,
        stage1_tp_pct: float = 0.25,
        trail_drawdown_pct: float = 0.30,
        timeout_hours: float = 2.0,
        stage1_sell_mode: str = "notional",
        stage1_sell_ratio: float = 0.50,
        pre_stage1_trail_enable: bool = False,
        pre_stage1_trail_activate_pct: float = 0.15,
        pre_stage1_trail_drawdown_pct: float = 0.40,
        timeout_extend_if_profitable: bool = False,
        timeout_extend_hours: float = 1.0,
        trail_dynamic: bool = True,
        early_stop_pct: float = 0.0,
        early_stop_sec: int = 0,
        momentum_sec: int = 0,
        momentum_activate_pct: float = 0.0,
        momentum_exit_pct: float = 0.0,
    ) -> StrategyOrder:
        entry = cls.buy_fill_price(mark, buy_slip)
        qty = notional_usd / entry
        return cls(
            chain=chain,
            token=token,
            entry_price=entry,
            open_mark=mark,
            notional_usd=notional_usd,
            qty=qty,
            cost_basis=entry,
            peak_price=mark,
            stage1_done=False,
            opened_at=opened_at,
            buy_slip=buy_slip,
            sell_slip=sell_slip,
            hard_stop_pct=hard_stop_pct,
            stage1_tp_pct=stage1_tp_pct,
            trail_drawdown_pct=trail_drawdown_pct,
            timeout_hours=timeout_hours,
            stage1_sell_mode=stage1_sell_mode,
            stage1_sell_ratio=stage1_sell_ratio,
            pre_stage1_trail_enable=pre_stage1_trail_enable,
            pre_stage1_trail_activate_pct=pre_stage1_trail_activate_pct,
            pre_stage1_trail_drawdown_pct=pre_stage1_trail_drawdown_pct,
            timeout_extend_if_profitable=timeout_extend_if_profitable,
            timeout_extend_hours=timeout_extend_hours,
            trail_dynamic=trail_dynamic,
            early_stop_pct=early_stop_pct,
            early_stop_sec=early_stop_sec,
            momentum_sec=momentum_sec,
            momentum_activate_pct=momentum_activate_pct,
            momentum_exit_pct=momentum_exit_pct,
        )

    def note_mark(self, mark: float) -> None:
        if mark > self.peak_price:
            self.peak_price = mark

    def stage1_sell_qty(self, mark: float) -> float:
        if self.stage1_sell_mode == "ratio":
            # Fixed ratio mode: sell a set percentage of current qty
            return self.qty * self.stage1_sell_ratio
        # Notional mode (default): sell enough to recover original notional
        sell_px = self.sell_fill_price(mark, self.sell_slip)
        if sell_px <= 0:
            return self.qty
        need = self.notional_usd / sell_px
        return min(self.qty, need)

    def evaluate(self, mark: float, now: float) -> tuple[Action, str | None, float]:
        """Return (action, reason, qty_to_sell)."""
        self.note_mark(mark)

        # No-momentum exit: never rose 2% above open_mark and now at/below -5%
        # within the momentum window -> leave at a fixed small loss.
        if (
            self.momentum_sec > 0
            and self.peak_price < self.open_mark * (1.0 + self.momentum_activate_pct)
            and mark <= self.open_mark * (1.0 + self.momentum_exit_pct)
            and (now - self.opened_at) < self.momentum_sec
        ):
            return Action.CLOSE, "no_momentum", self.qty

        stop_pct = self.hard_stop_pct
        stop_reason = "hard_stop"
        if (
            self.early_stop_sec > 0
            and self.early_stop_pct > self.hard_stop_pct  # tighter (higher) stop
            and (now - self.opened_at) < self.early_stop_sec
        ):
            stop_pct = self.early_stop_pct
            stop_reason = "early_stop"
        if mark <= self.open_mark * (1.0 + stop_pct):
            return Action.CLOSE, stop_reason, self.qty

        # Pre-stage1 trail: protects unrealized profit if the price pumped well past
        # the activation threshold but dumps back before ever hitting stage1_tp_pct.
        if (
            not self.stage1_done
            and self.pre_stage1_trail_enable
            and self.peak_price >= self.open_mark * (1.0 + self.pre_stage1_trail_activate_pct)
            and mark <= self.peak_price * (1.0 - self.pre_stage1_trail_drawdown_pct)
        ):
            return Action.CLOSE, "pre_stage1_trail", self.qty

        elapsed_h = (now - self.opened_at) / 3600.0

        # Base timeout before stage1: never "save" a late stage1 into an extend window.
        if not self.stage1_done and elapsed_h >= self.timeout_hours:
            return Action.CLOSE, "timeout", self.qty

        if not self.stage1_done:
            target = self.cost_basis * (1.0 + self.stage1_tp_pct)
            if mark >= target:
                qty = self.stage1_sell_qty(mark)
                if qty >= self.qty - 1e-12:
                    return Action.CLOSE, "stage1_full", self.qty
                return Action.STAGE1_SELL, "stage1", qty
            return Action.HOLD, None, 0.0

        # After stage1: optional extend only if already stage1_done and still profitable.
        timeout_limit_hours = self.timeout_hours
        if self.timeout_extend_if_profitable and mark > self.cost_basis:
            timeout_limit_hours = self.timeout_hours + self.timeout_extend_hours
        if elapsed_h >= timeout_limit_hours:
            return Action.CLOSE, "timeout", self.qty

        # Trail applies only after stage1; peak is still tracked from entry.
        drawdown = self.trail_drawdown_pct
        if self.trail_dynamic and self.open_mark > 0:
            peak_ratio = self.peak_price / self.open_mark
            if peak_ratio > 5:
                drawdown = 0.15
            elif peak_ratio > 2:
                drawdown = 0.20
        if self.peak_price > 0 and mark <= self.peak_price * (1.0 - drawdown):
            return Action.CLOSE, "trail", self.qty

        return Action.HOLD, None, 0.0

    def apply_stage1(self, mark: float, sell_qty: float) -> float:
        sell_px = self.sell_fill_price(mark, self.sell_slip)
        proceeds = sell_qty * sell_px
        cost_of_sold = sell_qty * self.cost_basis
        pnl = proceeds - cost_of_sold
        self.qty -= sell_qty
        self.cost_basis = sell_px
        self.stage1_done = True
        return pnl

    def apply_close(self, mark: float, sell_qty: float | None = None) -> float:
        qty = self.qty if sell_qty is None else sell_qty
        sell_px = self.sell_fill_price(mark, self.sell_slip)
        proceeds = qty * sell_px
        cost = qty * self.cost_basis
        pnl = proceeds - cost
        self.qty -= qty
        return pnl
