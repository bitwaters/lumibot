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
    # None = successfully acquired; str = rejected with a reason
    assert [a, b].count(None) == 1
    await db.close()


@pytest.mark.asyncio
async def test_paper_open_atomic_skip_second(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    r = await asyncio.gather(
        db.try_open_paper("sol", "tok", 1.05, 20.0 / 1.05, 20.0, peak_price=1.0),
        db.try_open_paper("sol", "tok", 1.1, 18.0, 20.0, peak_price=1.0),
    )
    opened = [pid for pid, reason in r if pid is not None]
    assert len(opened) == 1
    assert sum(1 for pid, reason in r if reason == "already_open") == 1
    summary = await db.paper_stats_summary()
    assert summary["opened_count"] == 1
    assert summary["skipped_open_count"] == 1
    await db.close()


@pytest.mark.asyncio
async def test_paper_open_respects_max_concurrent_atomically(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    a, ra = await db.try_open_paper(
        "sol", "a", 1.0, 20.0, 20.0, peak_price=1.0, max_concurrent=2
    )
    b, rb = await db.try_open_paper(
        "sol", "b", 1.0, 20.0, 20.0, peak_price=1.0, max_concurrent=2
    )
    assert a is not None and ra is None
    assert b is not None and rb is None
    c, rc = await db.try_open_paper(
        "sol", "c", 1.0, 20.0, 20.0, peak_price=1.0, max_concurrent=2
    )
    assert c is None and rc == "max_concurrent"
    summary = await db.paper_stats_summary("sol")
    assert summary["open_count"] == 2
    assert summary["skipped_open_count"] == 1
    # Concurrent race on two new tokens at the limit still cannot exceed max.
    await db.reset_paper_experiment("sol")
    for i in range(2):
        pid, _ = await db.try_open_paper(
            "sol", f"x{i}", 1.0, 20.0, 20.0, peak_price=1.0, max_concurrent=2
        )
        assert pid is not None
    raced = await asyncio.gather(
        db.try_open_paper("sol", "race1", 1.0, 20.0, 20.0, peak_price=1.0, max_concurrent=2),
        db.try_open_paper("sol", "race2", 1.0, 20.0, 20.0, peak_price=1.0, max_concurrent=2),
    )
    opened = [pid for pid, reason in raced if pid is not None]
    blocked = [reason for pid, reason in raced if reason == "max_concurrent"]
    assert len(opened) == 0
    assert len(blocked) == 2
    assert await db.count_open_papers("sol") == 2
    await db.close()


@pytest.mark.asyncio
async def test_config_loads_disabled_draft_chains():
    from lumibot.config import load_app_config

    cfg = load_app_config("config/chains.yaml")
    assert cfg.chains["sol"].enabled
    assert cfg.chains["bsc"].calibration_status == "calibrated"
    assert cfg.chains["bsc"].enabled
    assert cfg.chains["robinhood"].calibration_status == "calibrated"
    assert cfg.chains["robinhood"].enabled
