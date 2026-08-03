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
    hard_stop_pct: float = -0.50
    stage1_tp_pct: float = 0.30
    trail_drawdown_pct: float = 0.50
    timeout_hours: float = 4.0

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
        hard_stop_pct: float = -0.50,
        stage1_tp_pct: float = 0.30,
        trail_drawdown_pct: float = 0.50,
        timeout_hours: float = 4.0,
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
        )

    def note_mark(self, mark: float) -> None:
        if mark > self.peak_price:
            self.peak_price = mark

    def stage1_sell_qty(self, mark: float) -> float:
        sell_px = self.sell_fill_price(mark, self.sell_slip)
        if sell_px <= 0:
            return self.qty
        need = self.notional_usd / sell_px
        return min(self.qty, need)

    def evaluate(self, mark: float, now: float) -> tuple[Action, str | None, float]:
        """Return (action, reason, qty_to_sell)."""
        self.note_mark(mark)

        if mark <= self.open_mark * (1.0 + self.hard_stop_pct):
            return Action.CLOSE, "hard_stop", self.qty

        if now - self.opened_at >= self.timeout_hours * 3600:
            return Action.CLOSE, "timeout", self.qty

        if not self.stage1_done:
            target = self.cost_basis * (1.0 + self.stage1_tp_pct)
            if mark >= target:
                qty = self.stage1_sell_qty(mark)
                if qty >= self.qty - 1e-12:
                    return Action.CLOSE, "stage1_full", self.qty
                return Action.STAGE1_SELL, "stage1", qty
            return Action.HOLD, None, 0.0

        # Trail applies only after stage1; peak is still tracked from entry.
        if self.peak_price > 0 and mark <= self.peak_price * (1.0 - self.trail_drawdown_pct):
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
