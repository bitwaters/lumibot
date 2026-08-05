from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from lumibot.config import load_app_config
from lumibot.db import Database
from lumibot.executors import PaperExecutor
from lumibot.exec_types import ExecResult
from lumibot.models import Source, TokenCandidate
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
            mc = 40_000
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
        self.edited: list[Any] = []
        self.narratives: list[str] = []
        self.calls: list[str] = []

    async def send_candidate(
        self,
        cand,
        paper=None,
        *,
        latency_sec=None,
        paper_status: str | None = None,
    ) -> tuple[bool, bool, list[tuple[int, int]]]:
        self.calls.append("send")
        if self.ok:
            self.sent.append(cand)
            if paper_status is not None:
                self.paper_status.append(paper_status)
            elif paper is not None:
                self.paper_status.append(paper.status)
            from lumibot.telegram_notify import render_card

            self.cards.append(
                render_card(cand, paper=paper, latency_sec=latency_sec, paper_status=paper_status)
            )
            message_id = len(self.sent)
            return True, True, [(1, message_id)]
        return False, False, []

    async def edit_candidate(
        self,
        cand,
        paper=None,
        *,
        latency_sec=None,
        message_ids: list[tuple[int, int]] | None = None,
        paper_status: str | None = None,
    ) -> tuple[bool, bool]:
        self.calls.append("edit")
        if not self.ok:
            return False, False
        if paper_status is not None:
            self.paper_status.append(paper_status)
        elif paper is not None:
            self.paper_status.append(paper.status)
        self.edited.append(cand)
        from lumibot.telegram_notify import render_card

        self.cards.append(
            render_card(cand, paper=paper, latency_sec=latency_sec, paper_status=paper_status)
        )
        return True, True

    async def send_paper_event(self, ev) -> tuple[bool, bool]:
        self.events.append(ev)
        return True, True

    async def edit_candidate_with_narrative(
        self,
        cand,
        paper=None,
        *,
        latency_sec=None,
        message_ids: list[tuple[int, int]] | None = None,
        paper_status: str | None = None,
        narrative_line: str = "",
    ) -> tuple[bool, bool]:
        self.calls.append("edit_narrative")
        self.narratives.append(narrative_line)
        return True, True


class FakeNarrative:
    def __init__(self, line: str | None, *, delay: float = 0.0) -> None:
        self.line = line
        self.delay = delay
        self.calls: list[str] = []

    async def narrative_for(self, cand, info) -> str | None:
        self.calls.append(cand.address)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.line


def _sol_cfg():
    return load_app_config("config/chains.yaml")


def _pass_info() -> dict[str, Any]:
    return {
        "symbol": "TEST",
        "market_cap": 40_000,
        "liquidity": 20_000,
        "top10_rate": 0.2,
        "holder_count": 200,
        "visiting_count": 400,
        "volume_1h": 50_000,
        "price": 1.0,
    }


def _pass_security_sol() -> dict[str, Any]:
    return {
        "is_honeypot": False,
        "renounced_mint": True,
        "renounced_freeze_account": True,
        "rug_ratio": 0.1,
        "bundler_rate": 0.1,
        "rat_trader_amount_rate": 0.1,
        "is_wash_trading": False,
    }


def _pass_security_evm() -> dict[str, Any]:
    return {
        "is_honeypot": False,
        "is_renounced": True,
        "is_open_source": True,
        "buy_tax": 0.0,
        "sell_tax": 0.0,
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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
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
    client.info["good"] = {**_pass_info(), "price": 1.0, "market_cap": 40_000}
    client.security["good"] = _pass_security_sol()
    client.prices["good"] = 2.5
    client.market_caps["good"] = 45_000
    await pipe._handle_signal(
        {
            "address": "good",
            "signal_type": 12,
            "symbol": "GOOD",
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "price": 2.45,  # within chase_max_pct of fresh quote 2.5
        }
    )
    assert len(notifier.sent) == 1
    assert notifier.sent[0].chain_tag == "SOL"
    assert notifier.paper_status == ["opening", "opened"]
    row = await db.get_open_paper("sol", "good")
    assert row is not None
    assert abs(float(row["open_mark"]) - 2.5) < 1e-9
    assert abs(float(row["peak_price"]) - 2.5) < 1e-9
    entry = StrategyOrder.buy_fill_price(2.5, app.chains["sol"].execution.slippage_buy_pct)
    assert abs(row["entry_price"] - entry) < 1e-9
    assert notifier.cards
    card = notifier.cards[0]
    assert "📡 <b>$TEST</b> · SOL" in card
    assert "⏳ 开仓中" in card
    edited_card = notifier.cards[-1]
    assert "✅ 已开仓" in edited_card
    assert "$45.0K" in card  # fresh quote MC on card, not gate snapshot
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
    client.market_caps["fresh"] = 45_000
    # Gate uses signal payload metrics; info supplies visiting + post-gate card fields.
    client.info["fresh"] = {
        "symbol": "LIVE",
        "liquidity": 55_000,
        "holder_count": 900,
        "visiting_count": 400,
        "volume_1h": 50_000,
        "price": 2.0,
        "market_cap": 45_000,
        "open_timestamp": int(time.time()) - 600,  # ~10 min old, within age filter window
        "stat": {"top_10_holder_rate": 0.15, "holder_count": 900},
    }
    await pipe._handle_signal(
        {
            "address": "fresh",
            "signal_type": 12,
            "symbol": "OLD",
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "price": 1.95,  # within chase_max_pct of fresh quote 2.0
        }
    )
    assert notifier.paper_status == ["opening", "opened"]
    card = notifier.cards[0]
    assert "$45.0K" in card
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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.paper_status == ["opening", "opened"]
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
            "market_cap": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "visiting_count": 300,
            "volume_1h": 50_000,
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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
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
        "market_cap": 40_000,
        "trigger_mc": 40_000,
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
            "market_cap": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "visiting_count": 300,
            "volume_1h": 50_000,
            "price": 1.0,
        }
    )
    assert len(notifier.sent) == 2
    opens = await db.list_open_papers("sol")
    assert len(opens) == 1
    summary = await db.paper_stats_summary()
    assert summary["opened_count"] == 1
    assert summary["skipped_open_count"] == 0


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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
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
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.paper_status == ["opening", "opened"]
    assert await db.get_open_paper("sol", "nomc") is not None
    assert "市值    —" in notifier.cards[0]
    assert "$100.0K" not in notifier.cards[0]


@pytest.mark.asyncio
async def test_exit_mc_aligned_to_fill_mark_not_later_quote(tmp_path):
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    notifier = FakeNotifier()
    # _manage_one now fetches price+MC in a single get_price_and_market_cap call,
    # so mark and exit_quote always agree. Both strategy evaluation and MC display use
    # the same quote (0.6 / 90K), fill_price = 0.6 * (1 - sell_slip=0.05) = 0.57.
    client.prices["hs"] = 0.6        # price used by get_price_and_market_cap (via get_fresh_snapshot)
    client.market_caps["hs"] = 90_000
    ex = PaperExecutor(
        db,
        client,
        "sol",
        app.chains["sol"],
        app.chains["sol"].strategy,
        "token_info",
        notifier=notifier,
    )
    opened = time.time() - 600  # beyond early_stop window so reason stays hard_stop
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
    # _exit_mc_fields receives fill_mark=mark (the quote price, not fill_price after slippage),
    # so _mc_from_price_ratio(mark_mc, mark, mark) = mark_mc * 1.0 = mark_mc = 90K.
    # entry_mc = mark_mc * (open_mark / mark) = 90K * (1.0 / 0.6) = 150K.
    assert abs(float(ev.exit_mc) - 90_000) < 1.0    # fill_mark == mark → no scaling
    assert abs(float(ev.entry_mc) - 90_000 * (1.0 / 0.6)) < 1.0
    await db.close()




@pytest.mark.asyncio
async def test_max_concurrent_positions_blocks_new_open(tmp_path):
    app = _sol_cfg()
    chain_cfg = app.chains["sol"].model_copy(deep=True)
    chain_cfg.execution.limits.max_concurrent_positions = 1
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    ex = PaperExecutor(db, client, "sol", chain_cfg, chain_cfg.strategy, "token_info")  # type: ignore[arg-type]
    cand1 = TokenCandidate(chain="sol", address="first", source=Source.SIGNAL, price=1.0)
    res1 = await ex.on_alert(cand1)
    assert res1.status == "opened"

    cand2 = TokenCandidate(chain="sol", address="second", source=Source.SIGNAL, price=1.0)
    res2 = await ex.on_alert(cand2)
    assert res2.status == "blocked_max_positions"
    assert await db.get_open_paper("sol", "second") is None
    summary = await db.paper_stats_summary("sol")
    assert summary["skipped_open_count"] == 1
    await db.close()


@pytest.mark.asyncio
async def test_max_concurrent_early_reject_does_not_take_cooldown(harness):
    pipe, client, notifier, db, app = harness
    app.chains["sol"].execution.limits.max_concurrent_positions = 1
    pipe.cfg = app.chains["sol"]
    # Seed one open so the early DB gate trips.
    await db.try_open_paper(
        "sol", "held", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0, symbol="H"
    )
    client.info["cap"] = _pass_info()
    client.security["cap"] = _pass_security_sol()
    client.prices["cap"] = 1.0
    await pipe._handle_signal(
        {
            "address": "cap",
            "signal_type": 12,
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.sent == []
    # No cooldown acquired — immediate retry possible once a slot frees.
    assert (
        await db.check_cooldown("sol", "cap", "signal:12", 45, 15)
    ) is None
    # Reject reason recorded for observability
    rows = await db.top_reject_reasons(10)
    assert any(r["reason"] == "max_concurrent_positions" for r in rows)


@pytest.mark.asyncio
async def test_blocked_max_race_releases_cooldown(harness):
    """If open races past the early count check, cooldown must still be released."""
    pipe, client, notifier, db, app = harness
    app.chains["sol"].execution.limits.max_concurrent_positions = 1
    pipe.cfg = app.chains["sol"]
    client.info["race"] = _pass_info()
    client.security["race"] = _pass_security_sol()
    client.prices["race"] = 1.0

    # Bypass early check by forcing count to look free, then fill before on_alert.
    original_count = db.count_open_papers

    async def _zero_then_real(chain: str) -> int:
        # First call (early gate) reports 0; subsequent calls use real count.
        db.count_open_papers = original_count  # type: ignore[method-assign]
        return 0

    db.count_open_papers = _zero_then_real  # type: ignore[method-assign]
    await db.try_open_paper(
        "sol", "held", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0
    )

    await pipe._handle_signal(
        {
            "address": "race",
            "signal_type": 12,
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.paper_status == ["opening", "blocked_max_positions"]
    assert (
        await db.check_cooldown("sol", "race", "signal:12", 45, 15)
    ) is None


@pytest.mark.asyncio
async def test_push_then_open_order_is_preserved(harness):
    pipe, client, notifier, db, _app = harness
    events: list[str] = []

    async def on_alert(_cand: TokenCandidate) -> ExecResult:
        events.append("on_alert")
        assert notifier.calls == ["send"]
        return ExecResult(status="opened")

    pipe.executor.on_alert = on_alert
    client.info["ord"] = _pass_info()
    client.security["ord"] = _pass_security_sol()
    await pipe._handle_signal(
        {
            "address": "ord",
            "signal_type": 12,
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert events == ["on_alert"]
    assert notifier.calls[0] == "send"
    assert "edit" in notifier.calls
    row = await db.get_open_paper("sol", "ord")
    # on_alert is mocked, so this path only validates sequencing.
    assert row is None


@pytest.mark.asyncio
async def test_executor_error_releases_cooldown_and_rejects(harness):
    pipe, client, notifier, db, _app = harness

    async def boom(_cand: TokenCandidate) -> ExecResult:
        raise RuntimeError("executor boom")

    pipe.executor.on_alert = boom
    client.info["boom"] = _pass_info()
    client.security["boom"] = _pass_security_sol()
    await pipe._handle_signal(
        {
            "address": "boom",
            "signal_type": 12,
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.calls == ["send", "edit"]
    assert notifier.paper_status == ["opening", "executor_error"]
    assert await db.get_open_paper("sol", "boom") is None
    assert (
        await db.check_cooldown("sol", "boom", "signal:12", 45, 15)
    ) is None
    rows = await db.top_reject_reasons(10)
    assert any(
        row["reason"] == "executor_error" and row["source"] == "signal" and row["count"] >= 1
        for row in rows
    )


@pytest.mark.asyncio
async def test_bsc_chainpipeline_smoke_signal_path(tmp_path):
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    notifier = FakeNotifier()
    pipe = ChainPipeline(
        "bsc",
        app.chains["bsc"],
        app,
        client,
        db,
        notifier,
    )

    client.info["bsc"] = _pass_info()
    client.security["bsc"] = _pass_security_evm()
    client.prices["bsc"] = 1.2
    await pipe._handle_signal(
        {
            "address": "bsc",
            "signal_type": 12,
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "symbol": "TEST",
            "name": "BSC",
        }
    )
    assert notifier.calls[0] == "send"
    assert await db.get_open_paper("bsc", "bsc") is not None
    await db.close()


@pytest.mark.asyncio
async def test_rh_chainpipeline_smoke_signal_path(tmp_path):
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    notifier = FakeNotifier()
    pipe = ChainPipeline(
        "robinhood",
        app.chains["robinhood"],
        app,
        client,
        db,
        notifier,
    )

    client.info["rh"] = _pass_info()
    client.security["rh"] = _pass_security_evm()
    client.prices["rh"] = 1.4
    await pipe._handle_signal(
        {
            "address": "rh",
            "signal_type": 12,
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "symbol": "TEST",
            "name": "RH",
        }
    )
    assert notifier.calls[0] == "send"
    assert await db.get_open_paper("robinhood", "rh") is not None
    await db.close()


@pytest.mark.asyncio
async def test_open_check_prevents_open_and_sends_skipped_status(harness):
    pipe, client, notifier, db, app = harness
    client.info["hold1"] = _pass_info()
    client.security["hold1"] = _pass_security_sol()
    # Seed an existing open to make precheck trigger.
    await db.try_open_paper(
        "sol",
        "hold1",
        1.0,
        20.0,
        20.0,
        peak_price=1.0,
        open_mark=1.0,
        symbol="SOL",
        max_concurrent=0,
    )

    await pipe._handle_signal(
        {
            "address": "hold1",
            "signal_type": 12,
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )

    assert notifier.calls == ["send"]
    assert notifier.paper_status == ["precheck_skipped_open"]
    # Since precheck short-circuits before open, it never calls on_alert/状态编辑 path.
    assert notifier.edited == []

    # No second open created.
    opens = await db.list_open_papers("sol")
    assert len(opens) == 1


@pytest.mark.asyncio
async def test_closed_snapshots_survive_long_gap(tmp_path):
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    client.prices["old"] = 0.5
    ex = PaperExecutor(db, client, "sol", app.chains["sol"], app.chains["sol"].strategy, "token_info")  # type: ignore[arg-type]
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
    missing = await db.missing_snapshot_offsets(cur.lastrowid, app.chains["sol"].strategy.snapshots_sec)
    assert missing == []
    await db.close()


@pytest.mark.asyncio
async def test_narrative_edit_fires_on_opened_only(tmp_path):
    """Opened cards get the async narrative edit; non-opened states never do."""
    app = _sol_cfg()
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    notifier = FakeNotifier()
    narrative = FakeNarrative("特朗普概念官方迷因币")
    pipe = ChainPipeline(
        "sol",
        app.chains["sol"],
        app,
        client,
        db,
        notifier,
        narrative=narrative,  # type: ignore[arg-type]
    )

    # opened path -> narrative lookup + edit
    client.info["n1"] = _pass_info()
    client.security["n1"] = _pass_security_sol()
    client.prices["n1"] = 1.0
    await pipe._handle_signal(
        {
            "address": "n1",
            "signal_type": 12,
            "symbol": "TRUMP",
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "price": 1.0,
        }
    )
    await asyncio.sleep(0)
    assert narrative.calls == ["n1"]
    assert notifier.calls.count("edit_narrative") == 1
    assert notifier.narratives == ["特朗普概念官方迷因币"]

    # narrative service absent -> no lookup, no edit
    notifier2 = FakeNotifier()
    pipe2 = ChainPipeline(
        "sol", app.chains["sol"], app, client, db, notifier2  # type: ignore[arg-type]
    )
    client.info["n2"] = _pass_info()
    client.security["n2"] = _pass_security_sol()
    client.prices["n2"] = 1.0
    await pipe2._handle_signal(
        {
            "address": "n2",
            "signal_type": 12,
            "symbol": "AGENT",
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "price": 1.0,
        }
    )
    await asyncio.sleep(0)
    assert notifier2.calls.count("edit_narrative") == 0

    # narrative returns None -> no edit
    notifier3 = FakeNotifier()
    pipe3 = ChainPipeline(
        "sol",
        app.chains["sol"],
        app,
        client,
        db,
        notifier3,
        narrative=FakeNarrative(None),  # type: ignore[arg-type]
    )
    client.info["n3"] = _pass_info()
    client.security["n3"] = _pass_security_sol()
    client.prices["n3"] = 1.0
    await pipe3._handle_signal(
        {
            "address": "n3",
            "signal_type": 12,
            "symbol": "TOKENX",
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "price": 1.0,
        }
    )
    await asyncio.sleep(0)
    assert notifier3.calls.count("edit_narrative") == 0

    # already_open state -> no narrative lookup, no edit
    await db.try_open_paper(
        "sol", "tokX", 1.0, 20.0, 20.0, peak_price=1.0, open_mark=1.0, symbol="TOKENX"
    )
    notifier4 = FakeNotifier()
    narrative4 = FakeNarrative("should-not-fire")
    pipe4 = ChainPipeline(
        "sol",
        app.chains["sol"],
        app,
        client,
        db,
        notifier4,
        narrative=narrative4,  # type: ignore[arg-type]
    )
    client.info["n4"] = _pass_info()
    client.security["n4"] = _pass_security_sol()
    client.prices["n4"] = 1.0
    await pipe4._handle_signal(
        {
            "address": "tokX",
            "signal_type": 12,
            "symbol": "TOKENX",
            "market_cap": 40_000,
            "trigger_mc": 40_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
            "price": 1.0,
        }
    )
    await asyncio.sleep(0)
    assert narrative4.calls == []
    assert notifier4.calls.count("edit_narrative") == 0
    await db.close()
