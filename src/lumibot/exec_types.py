from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ExecResult:
    """Result of trying to open a position after an alert."""

    status: str  # opened | skipped_open | no_price | blocked_live | noop
    entry_price: float | None = None
    notional_usd: float | None = None
    qty: float | None = None
    mark: float | None = None
    open_mark: float | None = None
    position_id: int | None = None
    buy_slip: float | None = None
    hard_stop_pct: float | None = None


@dataclass
class PaperTradeEvent:
    """Paper fill event for Telegram visibility."""

    kind: str  # stage1 | close
    chain: str
    token: str
    symbol: str | None
    reason: str
    mark: float
    fill_price: float
    qty: float
    pnl: float
    notional_usd: float
    entry_price: float
    remaining_qty: float = 0.0
