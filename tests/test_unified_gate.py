from __future__ import annotations

import time

import pytest

from lumibot.config import FiltersCfg, load_app_config
from lumibot.db import Database
from lumibot.filters import evaluate_mc_extension
from lumibot.models import Source, TokenCandidate
from lumibot.pipeline import ChainPipeline

from test_pipeline_integration import FakeClient, FakeNotifier, _pass_info, _pass_security_sol


def test_trending_window_is_1m():
    cfg = load_app_config("config/chains.yaml")
    assert cfg.chains["sol"].sources.trending.window == "1m"
    assert cfg.chains["bsc"].sources.trending.window == "1m"
    assert cfg.strategy.loss_cooldown_min == 180
    assert cfg.strategy.post_close_cooldown_min == 45


def test_mc_extension_soft_vs_enforce():
    cand = TokenCandidate(
        chain="sol",
        address="t",
        source=Source.SIGNAL,
        signal_type=12,
        market_cap=250_000,
        trigger_mc=100_000,
    )
    soft_cfg = FiltersCfg(
        mc_min=1,
        mc_max=1e9,
        liquidity_min=1,
        top10_max=1,
        holders_min=1,
        visiting_min=1,
        max_mc_extension=2.0,
        enforce_mc_extension=False,
    )
    soft = evaluate_mc_extension(cand, soft_cfg)
    assert soft.soft and not soft.reject and soft.reason == "mc_extension_soft"

    hard_cfg = soft_cfg.model_copy(update={"enforce_mc_extension": True})
    hard = evaluate_mc_extension(cand, hard_cfg)
    assert hard.reject and hard.reason == "mc_extension"


@pytest.mark.asyncio
async def test_loss_row_blocks_admission(tmp_path):
    app = load_app_config("config/chains.yaml")
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    now = time.time()
    await db.conn.execute(
        "INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)",
        ("sol", "blocked", "loss", now + 3600),
    )
    await db.conn.commit()
    assert await db.has_reentry_block("sol", "blocked") == "loss"

    client = FakeClient()
    client.info["blocked"] = _pass_info()
    client.security["blocked"] = _pass_security_sol()
    notifier = FakeNotifier(ok=True)
    pipe = ChainPipeline("sol", app.chains["sol"], app, client, db, notifier)  # type: ignore[arg-type]
    await pipe._handle_signal(
        {
            "address": "blocked",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.sent == []
    cur = await db.conn.execute(
        "SELECT count FROM reject_counts WHERE reason='loss_cooldown'"
    )
    row = await cur.fetchone()
    assert row is not None and int(row["count"]) >= 1
    await db.close()


@pytest.mark.asyncio
async def test_close_arms_loss_and_post_close(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    pos_id = await db.try_open_paper(
        "sol", "tok", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0
    )
    assert pos_id is not None
    await db.close_paper(
        pos_id,
        0.76,
        20 / 1.05,
        15.0,
        "hard_stop",
        -5.0,
        loss_cooldown_min=180,
        post_close_cooldown_min=45,
    )
    assert await db.has_reentry_block("sol", "tok") == "loss"
    await db.close()


@pytest.mark.asyncio
async def test_duration_zero_disables_arming(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    pos_id = await db.try_open_paper(
        "sol", "tok2", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0
    )
    assert pos_id is not None
    await db.close_paper(
        pos_id,
        0.76,
        20 / 1.05,
        15.0,
        "hard_stop",
        -5.0,
        loss_cooldown_min=0,
        post_close_cooldown_min=0,
    )
    assert await db.has_reentry_block("sol", "tok2") is None
    await db.close()


@pytest.mark.asyncio
async def test_abort_does_not_arm_reentry(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    pos_id = await db.try_open_paper(
        "sol", "abort", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0
    )
    assert pos_id is not None
    await db.abort_paper_open(pos_id)
    assert await db.get_open_paper("sol", "abort") is None
    assert await db.has_reentry_block("sol", "abort") is None
    await db.close()


@pytest.mark.asyncio
async def test_backfill_open_mark(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    await db.conn.execute(
        """
        INSERT INTO paper_positions(
          chain, token, status, entry_price, open_mark, qty, notional_usd, cost_basis,
          peak_price, stage1_done, opened_at
        ) VALUES(?,?,?,?,?,?,?,?,?,0,?)
        """,
        ("sol", "old", "open", 1.05, None, 20, 20, 1.05, 1.05, time.time()),
    )
    await db.conn.commit()
    n = await db.backfill_open_mark({"sol": 0.05})
    assert n == 1
    row = await db.get_open_paper("sol", "old")
    assert row is not None
    assert abs(float(row["open_mark"]) - 1.0) < 1e-9
    await db.close()


@pytest.mark.asyncio
async def test_acquire_recheck_releases_on_loss(tmp_path):
    """Simulate loss armed between acquire and open: release and reject."""
    app = load_app_config("config/chains.yaml")
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    client.info["race"] = _pass_info()
    client.security["race"] = _pass_security_sol()
    notifier = FakeNotifier(ok=True)
    pipe = ChainPipeline("sol", app.chains["sol"], app, client, db, notifier)  # type: ignore[arg-type]

    orig_acquire = db.try_acquire_cooldown

    async def acquire_then_arm_loss(*args, **kwargs):
        ok = await orig_acquire(*args, **kwargs)
        if ok:
            now = time.time()
            await db.conn.execute(
                """
                INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)
                ON CONFLICT(chain, token, kind) DO UPDATE SET until_ts=excluded.until_ts
                """,
                ("sol", "race", "loss", now + 3600),
            )
            await db.conn.commit()
        return ok

    db.try_acquire_cooldown = acquire_then_arm_loss  # type: ignore[method-assign]
    await pipe._handle_signal(
        {
            "address": "race",
            "signal_type": 12,
            "market_cap": 100_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert notifier.sent == []
    assert await db.get_open_paper("sol", "race") is None
    # source cooldown released
    cur = await db.conn.execute(
        "SELECT 1 FROM cooldowns WHERE chain=? AND token=? AND kind=? AND until_ts>?",
        ("sol", "race", "signal:12", time.time()),
    )
    assert await cur.fetchone() is None
    await db.close()


@pytest.mark.asyncio
async def test_soft_extension_allows_open(tmp_path):
    app = load_app_config("config/chains.yaml")
    assert app.chains["sol"].filters.enforce_mc_extension is False
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    client = FakeClient()
    info = _pass_info()
    info["market_cap"] = 250_000
    client.info["ext"] = info
    client.security["ext"] = _pass_security_sol()
    client.prices["ext"] = 1.0
    notifier = FakeNotifier(ok=True)
    pipe = ChainPipeline("sol", app.chains["sol"], app, client, db, notifier)  # type: ignore[arg-type]
    await pipe._handle_signal(
        {
            "address": "ext",
            "signal_type": 12,
            "market_cap": 250_000,
            "trigger_mc": 100_000,
            "liquidity": 20_000,
            "top10_rate": 0.2,
            "holder_count": 200,
        }
    )
    assert len(notifier.sent) == 1
    cur = await db.conn.execute(
        "SELECT count FROM reject_counts WHERE reason='mc_extension_soft'"
    )
    row = await cur.fetchone()
    assert row is not None and int(row["count"]) >= 1
    await db.close()
