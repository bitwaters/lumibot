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
        self.market_caps: dict[str, float | None] = {}
        # Optional post-fill quote price (defaults to prices[address]).
        self.exit_quote_prices: dict[str, float] = {}
        self.quote_fail: bool = False
        self.limiter = type("L", (), {"available": AsyncMock(return_value=20)})()

    async def get_token_info(self, chain: str, address: str, *, use_cache: bool = True):
        return self.info.get(address, {})

    async def get_token_security(self, chain: str, address: str):
        return self.security.get(address, {})

    async def get_price(self, chain: str, address: str, source: str = "token_info"):
        if self.quote_fail:
            return None
        return self.prices.get(address, 1.0)

    async def get_price_and_market_cap(self, chain: str, address: str, source: str = "token_info"):
        price, mc, _info = await self.get_fresh_snapshot(chain, address, source)
        return price, mc

    async def get_fresh_snapshot(self, chain: str, address: str, source: str = "token_info"):
        if self.quote_fail:
            return None, None, {}
        price = self.exit_quote_prices.get(address, self.prices.get(address, 1.0))
        if address in self.market_caps:
            mc = self.market_caps[address]
        else:
            mc = 100_000
        info = dict(self.info.get(address, {}))
        if "price" not in info:
            info["price"] = price
        if mc is not None and "market_cap" not in info:
            info["market_cap"] = mc
        return price, mc, info


class FakeNotifier:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[Any] = []
        self.paper_status: list[str] = []
        self.cards: list[str] = []
        self.events: list[Any] = []

    async def send_candidate(self, cand, paper=None, *, latency_sec=None) -> tuple[bool, bool]:
        if self.ok:
            self.sent.append(cand)
            if paper is not None:
                self.paper_status.append(paper.status)
            from lumibot.telegram_notify import render_card

            self.cards.append(render_card(cand, paper=paper, latency_sec=latency_sec))
            return True, True
        return False, False

    async def send_paper_event(self, ev) -> tuple[bool, bool]:
        self.events.append(ev)
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
    # Enrich snapshot uses stale price/mc; post-gate quote must win for open + card MC.
    client.info["good"] = {**_pass_info(), "price": 1.0, "market_cap": 100_000}
    client.security["good"] = _pass_security_sol()
    client.prices["good"] = 2.5
    client.market_caps["good"] = 250_000
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
            "price": 1.0,
        }
    )
    assert len(notifier.sent) == 1
    assert notifier.sent[0].chain_tag == "SOL"
    assert notifier.paper_status == ["opened"]
    row = await db.get_open_paper("sol", "good")
    assert row is not None
    assert abs(float(row["open_mark"]) - 2.5) < 1e-9
    assert abs(float(row["peak_price"]) - 2.5) < 1e-9
    entry = StrategyOrder.buy_fill_price(2.5, app.chains["sol"].execution.slippage_buy_pct)
    assert abs(row["entry_price"] - entry) < 1e-9
    assert notifier.cards
    card = notifier.cards[0]
    assert "📡 [SOL] 信号推送" in card
    assert "✅ 已开仓" in card
    assert "$250.0K" in card  # fresh quote MC on card, not gate 100K
    cur = await db.conn.execute("SELECT payload_json FROM alerts ORDER BY id DESC LIMIT 1")
    alert = await cur.fetchone()
    assert alert is not None
    import json

    payload = json.loads(alert["payload_json"])
    assert payload.get("exec_status") == "opened"
    assert "latency_ms" in payload


@pytest.mark.asyncio
async def test_push_card_uses_fresh_snapshot_not_gate_metrics(harness):
    pipe, client, notifier, db, _app = harness
    client.security["fresh"] = _pass_security_sol()
    client.prices["fresh"] = 2.0
    client.market_caps["fresh"] = 220_000
    # Gate uses signal payload metrics; info supplies visiting + post-gate card fields.
    client.info["fresh"] = {
        "symbol": "LIVE",
        "liquidity": 55_000,
        "holder_count": 900,
        "visiting_count": 400,
        "price": 2.0,
        "market_cap": 220_000,
        "open_timestamp": 1_700_000_000,
        "stat": {"top_10_holder_rate": 0.15, "holder_count": 900},
    }
    await pipe._handle_signal(
        {
            "address": "fresh",
            "signal_type": 12,
            "symbol": "OLD",
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "price": 1.0,
        }
    )
    assert notifier.paper_status == ["opened"]
    card = notifier.cards[0]
    assert "$220.0K" in card
    assert "$55.0K" in card
    assert "900" in card
    assert "400" in card
    assert "15.0%" in card
    assert "$LIVE" in card
    row = await db.get_open_paper("sol", "fresh")
    assert abs(float(row["open_mark"]) - 2.0) < 1e-9


@pytest.mark.asyncio
async def test_fresh_quote_mc_outside_filter_still_opens(harness):
    """Post-gate MC must not re-run light filters / mc_extension."""
    pipe, client, notifier, db, _app = harness
    client.info["wide"] = _pass_info()
    client.security["wide"] = _pass_security_sol()
    client.prices["wide"] = 1.0
    # Far above typical mc_max — would fail if re-filtered.
    client.market_caps["wide"] = 50_000_000
    await pipe._handle_signal(
        {
            "address": "wide",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.paper_status == ["opened"]
    assert await db.get_open_paper("sol", "wide") is not None
    assert "$50.00M" in notifier.cards[0]


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
    # TG fail aborted the open — no residual paper
    assert await db.get_open_paper("sol", "x") is None
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
    assert await db.get_open_paper("sol", "x") is not None
    # abort must not arm loss/post_close
    assert await db.has_reentry_block("sol", "x") is None


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
async def test_post_gate_quote_failure_no_push(harness):
    pipe, client, notifier, db, _app = harness
    client.info["np"] = _pass_info()
    client.security["np"] = _pass_security_sol()
    client.quote_fail = True
    await pipe._handle_signal(
        {
            "address": "np",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.sent == []
    assert await db.get_open_paper("sol", "np") is None
    cur = await db.conn.execute(
        "SELECT count FROM reject_counts WHERE reason='no_price'"
    )
    row = await cur.fetchone()
    assert row is not None and int(row["count"]) >= 1
    # cooldown released — can acquire again after quote recovers
    client.quote_fail = False
    client.prices["np"] = 1.0
    await pipe._handle_signal(
        {
            "address": "np",
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
async def test_fresh_quote_without_mc_clears_card_mc(harness):
    pipe, client, notifier, db, _app = harness
    client.info["nomc"] = _pass_info()
    client.security["nomc"] = _pass_security_sol()
    client.prices["nomc"] = 1.2
    client.market_caps["nomc"] = None
    await pipe._handle_signal(
        {
            "address": "nomc",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.paper_status == ["opened"]
    assert await db.get_open_paper("sol", "nomc") is not None
    assert "💰 市值 —" in notifier.cards[0]
    assert "$100.0K" not in notifier.cards[0]


@pytest.mark.asyncio
async def test_exit_mc_aligned_to_fill_mark_not_later_quote(tmp_path):
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    notifier = FakeNotifier()
    # Fill/evaluate at hard-stop mark 0.8; later display quote rebounds to 0.9 / 90K MC.
    client.prices["hs"] = 0.8
    client.exit_quote_prices["hs"] = 0.9
    client.market_caps["hs"] = 90_000
    ex = PaperExecutor(
        db,
        client,
        "sol",
        app.chains["sol"],
        app.strategy,
        "token_info",
        notifier=notifier,
    )
    opened = time.time() - 60
    await db.conn.execute(
        """
        INSERT INTO paper_positions(
          chain, token, symbol, status, entry_price, open_mark, qty, notional_usd,
          cost_basis, peak_price, stage1_done, opened_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)
        """,
        ("sol", "hs", "HS", "open", 1.05, 1.0, 20.0, 20.0, 1.05, 1.0, opened),
    )
    await db.conn.commit()
    await ex.manage_open_positions()
    assert len(notifier.events) == 1
    ev = notifier.events[0]
    assert ev.reason == "hard_stop"
    assert abs(float(ev.exit_mc) - 80_000) < 1e-6  # 90K * (0.8/0.9)
    assert abs(float(ev.entry_mc) - 100_000) < 1e-6  # 90K * (1.0/0.9)
    await db.close()


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
