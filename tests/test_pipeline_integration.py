from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from lumibot.config import load_app_config
from lumibot.db import Database
from lumibot.executors import PaperExecutor
from lumibot.pipeline import ChainPipeline
from lumibot.strategy import StrategyOrder


class FakeClient:
    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.security: dict[str, Any] = {}
        self.prices: dict[str, float] = {}
        self.limiter = type("L", (), {"available": AsyncMock(return_value=20)})()

    async def get_token_info(self, chain: str, address: str, *, use_cache: bool = True):
        return self.info.get(address, {})

    async def get_token_security(self, chain: str, address: str):
        return self.security.get(address, {})

    async def get_price(self, chain: str, address: str, source: str = "token_info"):
        return self.prices.get(address, 1.0)


class FakeNotifier:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[Any] = []
        self.paper_status: list[str] = []

    async def send_candidate(self, cand, paper=None) -> tuple[bool, bool]:
        if self.ok:
            self.sent.append(cand)
            if paper is not None:
                self.paper_status.append(paper.status)
            return True, True
        return False, False

    async def send_paper_event(self, ev) -> tuple[bool, bool]:
        return True, True


def _sol_cfg():
    return load_app_config("config/chains.yaml")


def _pass_info() -> dict[str, Any]:
    return {
        "symbol": "TEST",
        "market_cap": 100_000,
        "liquidity": 20_000,
        "top10_rate": 0.2,
        "holder_count": 200,
        "visiting_count": 150,
        "price": 1.0,
    }


def _pass_security_sol() -> dict[str, Any]:
    return {
        "renounced_mint": True,
        "renounced_freeze_account": True,
        "rug_ratio": 0.1,
        "bundler_rate": 0.1,
        "rat_trader_amount_rate": 0.1,
        "is_wash_trading": False,
    }


@pytest.fixture
async def harness(tmp_path):
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    notifier = FakeNotifier(ok=True)
    pipe = ChainPipeline("sol", app.chains["sol"], app, client, db, notifier)  # type: ignore[arg-type]
    yield pipe, client, notifier, db, app
    await db.close()


@pytest.mark.asyncio
async def test_reject_before_telegram(harness):
    pipe, client, notifier, db, _app = harness
    client.info["bad"] = {**_pass_info(), "visiting_count": 1}
    client.security["bad"] = _pass_security_sol()
    await pipe._handle_signal(
        {
            "address": "bad",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.sent == []
    cur = await db.conn.execute("SELECT reason, count FROM reject_counts")
    rows = {r["reason"]: r["count"] for r in await cur.fetchall()}
    assert rows.get("visiting", 0) >= 1


@pytest.mark.asyncio
async def test_signal_visiting_missing_from_info_rejects(harness):
    pipe, client, notifier, _db, _app = harness
    info = _pass_info()
    del info["visiting_count"]
    client.info["tok"] = info
    client.security["tok"] = _pass_security_sol()
    await pipe._handle_signal(
        {
            "address": "tok",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "visiting_count": 9999,  # payload must be ignored
        }
    )
    assert notifier.sent == []


@pytest.mark.asyncio
async def test_happy_path_alerts_and_opens_paper(harness):
    pipe, client, notifier, db, app = harness
    client.info["good"] = _pass_info()
    client.security["good"] = _pass_security_sol()
    client.prices["good"] = 1.0
    await pipe._handle_signal(
        {
            "address": "good",
            "signal_type": 12,
            "symbol": "GOOD",
            "market_cap": 100_000,
            "trigger_mc": 120_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert len(notifier.sent) == 1
    assert notifier.sent[0].chain_tag == "SOL"
    assert notifier.paper_status == ["opened"]
    row = await db.get_open_paper("sol", "good")
    assert row is not None
    assert row["peak_price"] == 1.0
    entry = StrategyOrder.buy_fill_price(1.0, app.chains["sol"].execution.slippage_buy_pct)
    assert abs(row["entry_price"] - entry) < 1e-9


@pytest.mark.asyncio
async def test_safety_reject_no_alert(harness):
    pipe, client, notifier, _db, _app = harness
    client.info["rug"] = _pass_info()
    client.security["rug"] = {**_pass_security_sol(), "rug_ratio": 0.9}
    await pipe._handle_trending(
        {
            "address": "rug",
            "market_cap": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "visiting_count": 150,
            "price": 1.0,
        }
    )
    assert notifier.sent == []


@pytest.mark.asyncio
async def test_tg_failure_releases_cooldown(harness):
    pipe, client, notifier, db, _app = harness
    notifier.ok = False
    client.info["x"] = _pass_info()
    client.security["x"] = _pass_security_sol()
    await pipe._handle_signal(
        {
            "address": "x",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.sent == []
    # cooldown released → second attempt can acquire again
    notifier.ok = True
    await pipe._handle_signal(
        {
            "address": "x",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert len(notifier.sent) == 1


@pytest.mark.asyncio
async def test_paper_skip_second_open_still_alerts(harness):
    pipe, client, notifier, db, app = harness
    client.info["dup"] = _pass_info()
    client.security["dup"] = _pass_security_sol()
    client.prices["dup"] = 1.0
    raw = {
        "address": "dup",
        "signal_type": 12,
        "market_cap": 100_000,
        "trigger_mc": 100_000,
        "liquidity": 20_000,
        "top10_rate": 0.2,
        "holder_count": 200,
    }
    await pipe._handle_signal(raw)
    # Force cooldown clear to allow second alert path for same type in test
    await db.release_cooldown("sol", "dup", "signal:12")
    await pipe._handle_trending(
        {
            "address": "dup",
            "market_cap": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "visiting_count": 150,
            "price": 1.0,
        }
    )
    assert len(notifier.sent) == 2
    opens = await db.list_open_papers("sol")
    assert len(opens) == 1


@pytest.mark.asyncio
async def test_closed_snapshots_survive_long_gap(tmp_path):
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    client.prices["old"] = 0.5
    ex = PaperExecutor(db, client, "sol", app.chains["sol"], app.strategy, "token_info")  # type: ignore[arg-type]
    opened = time.time() - 10_000  # well beyond prior 1h cutoff
    cur = await db.conn.execute(
        """
        INSERT INTO paper_positions(
          chain, token, status, entry_price, qty, notional_usd, cost_basis,
          peak_price, stage1_done, opened_at, closed_at, close_reason
        ) VALUES(?,?,?,?,?,?,?,?,0,?,?,?)
        """,
        ("sol", "old", "closed", 1.0, 0, 20, 1.0, 1.0, opened, time.time(), "timeout"),
    )
    await db.conn.commit()
    assert cur.lastrowid is not None
    await ex.manage_open_positions()
    missing = await db.missing_snapshot_offsets(cur.lastrowid, app.strategy.snapshots_sec)
    assert missing == []
    await db.close()
