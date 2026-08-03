import asyncio

import pytest

from lumibot.db import Database


@pytest.mark.asyncio
async def test_cooldown_atomic_only_one(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()

    async def race():
        return await asyncio.gather(
            db.try_acquire_cooldown("sol", "tok", "signal:12", 45, 15),
            db.try_acquire_cooldown("sol", "tok", "trending", 45, 15),
        )

    a, b = await race()
    assert (a, b).count(True) == 1
    await db.close()


@pytest.mark.asyncio
async def test_paper_open_atomic_skip_second(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    r = await asyncio.gather(
        db.try_open_paper("sol", "tok", 1.05, 20.0 / 1.05, 20.0, peak_price=1.0),
        db.try_open_paper("sol", "tok", 1.1, 18.0, 20.0, peak_price=1.0),
    )
    opened = [x for x in r if x is not None]
    assert len(opened) == 1
    summary = await db.paper_stats_summary()
    assert summary["opened_count"] == 1
    assert summary["skipped_open_count"] == 1
    await db.close()


@pytest.mark.asyncio
async def test_config_loads_disabled_draft_chains():
    from lumibot.config import load_app_config

    cfg = load_app_config("config/chains.yaml")
    assert cfg.chains["sol"].enabled
    assert cfg.chains["bsc"].calibration_status == "draft"
    assert not cfg.chains["bsc"].enabled
    assert cfg.chains["robinhood"].calibration_status == "draft"
    assert not cfg.chains["robinhood"].enabled
