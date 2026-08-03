from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Source(str, Enum):
    SIGNAL = "signal"
    TRENDING = "trending"


@dataclass
class NormalizedSafety:
    hard_fail: bool = False
    reason: str | None = None
    warnings: list[str] = field(default_factory=list)
    honeypot: bool | None = None
    renounced: bool | None = None
    open_source: bool | None = None
    renounced_mint: bool | None = None
    renounced_freeze: bool | None = None
    buy_tax: float | None = None
    sell_tax: float | None = None
    rug_ratio: float | None = None
    bundler_rate: float | None = None
    rat_rate: float | None = None
    wash_trading: bool | None = None
    creator_hold: bool | None = None


@dataclass
class TokenCandidate:
    chain: str
    address: str
    source: Source
    signal_type: int | None = None
    symbol: str | None = None
    name: str | None = None
    market_cap: float | None = None
    trigger_mc: float | None = None
    liquidity: float | None = None
    holder_count: float | None = None
    top10_rate: float | None = None
    visiting_count: float | None = None
    price: float | None = None
    platform: str | None = None
    safety: NormalizedSafety | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    seen_at: float | None = None
    open_timestamp: float | None = None

    @property
    def source_key(self) -> str:
        if self.source == Source.SIGNAL:
            return f"signal:{self.signal_type or 0}"
        return "trending"

    @property
    def chain_tag(self) -> str:
        return {"sol": "SOL", "bsc": "BSC", "robinhood": "RH"}.get(self.chain, self.chain.upper())
