import json

import pytest

from lumibot.db import Database


async def _fill_count(db: Database) -> int:
    cur = await db.conn.execute("SELECT COUNT(*) AS n FROM paper_fills")
    row = await cur.fetchone()
    return int(row["n"])


@pytest.mark.asyncio
async def test_reset_paper_experiment_clears_cohort_and_stats(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    pos, _ = await db.try_open_paper(
        "sol", "tok", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0, symbol="T"
    )
    assert pos is not None
    assert await db.close_paper(
        pos,
        0.7,
        20 / 1.05,
        14.0,
        "hard_stop",
        -6.0,
        loss_cooldown_min=180,
        post_close_cooldown_min=45,
    )
    # Second open attempt while first (closed) is gone — reopen then skip via open position
    pos2, _ = await db.try_open_paper(
        "sol", "tok2", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0, symbol="T2"
    )
    assert pos2 is not None
    skip_id, skip_reason = await db.try_open_paper(
        "sol", "tok2", 1.1, 18.0, 20.0, peak_price=1.0, open_mark=1.0, symbol="T2"
    )
    assert skip_id is None and skip_reason == "already_open"
    await db.insert_alert(
        "sol",
        "tok",
        "signal:12",
        json.dumps({"exec_status": "opened", "symbol": "T"}),
    )
    await db.bump_reject("sol", "signal", "mc")

    before = await db.paper_stats_summary()
    assert before["opened_count"] == 2
    assert before["closed_count"] == 1
    assert before["hard_stop_count"] == 1
    assert before["skipped_open_count"] == 1
    assert await db.count_active_cooldowns() >= 1

    deleted = await db.reset_paper_experiment()
    assert deleted["paper_positions"] >= 1
    assert deleted["paper_skip_opens"] >= 1
    assert deleted["alerts"] >= 1
    assert deleted["reject_counts"] >= 1

    after = await db.paper_stats_summary()
    assert after["open_count"] == 0
    assert after["closed_count"] == 0
    assert after["opened_count"] == 0
    assert after["skipped_open_count"] == 0
    assert after["hard_stop_count"] == 0
    assert await db.count_active_cooldowns() == 0
    assert await db.list_recent_alerts(10) == []
    assert await db.top_reject_reasons(5) == []
    await db.close()


@pytest.mark.asyncio
async def test_reset_paper_experiment_scoped_to_chain(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    sol_pos, _ = await db.try_open_paper(
        "sol", "tok", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0, symbol="S"
    )
    bsc_pos, _ = await db.try_open_paper(
        "bsc", "tok", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0, symbol="B"
    )
    assert sol_pos is not None and bsc_pos is not None
    await db.insert_alert("sol", "tok", "signal:12", json.dumps({"symbol": "S"}))
    await db.insert_alert("bsc", "tok", "signal:12", json.dumps({"symbol": "B"}))
    await db.bump_reject("sol", "signal", "mc")
    await db.bump_reject("bsc", "signal", "mc")
    await db.insert_snapshot(sol_pos, 60, 1.0, position_closed=False)

    deleted = await db.reset_paper_experiment("bsc")
    assert deleted["paper_positions"] == 1
    assert deleted["alerts"] == 1
    assert deleted["reject_counts"] == 1

    # sol untouched — including fills/snapshots tied to sol positions
    assert await db.get_open_paper("sol", "tok") is not None
    sol_summary = await db.paper_stats_summary("sol")
    assert sol_summary["open_count"] == 1
    bsc_summary = await db.paper_stats_summary("bsc")
    assert bsc_summary["open_count"] == 0
    assert await db.get_open_paper("bsc", "tok") is None
    assert await db.count_open_papers("sol") == 1
    assert await db.count_open_papers("bsc") == 0
    assert len(await db.list_recent_alerts(10, chain="sol")) == 1
    assert len(await db.list_recent_alerts(10, chain="bsc")) == 0
    cur = await db.conn.execute(
        "SELECT COUNT(*) AS n FROM paper_fills WHERE position_id=?", (sol_pos,)
    )
    assert int((await cur.fetchone())["n"]) >= 1
    cur = await db.conn.execute(
        "SELECT COUNT(*) AS n FROM snapshots WHERE position_id=?", (sol_pos,)
    )
    assert int((await cur.fetchone())["n"]) == 1
    await db.close()


@pytest.mark.asyncio
async def test_close_and_partial_sell_noop_after_reset(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    pos, _ = await db.try_open_paper(
        "sol", "tok", 1.05, 20 / 1.05, 20.0, peak_price=1.0, open_mark=1.0, symbol="T"
    )
    assert pos is not None
    fills_before = await _fill_count(db)

    await db.reset_paper_experiment()
    assert await db.close_paper(pos, 0.7, 20 / 1.05, 14.0, "hard_stop", -6.0) is False
    assert (
        await db.add_partial_sell(pos, 1.2, 10.0, 12.0, 10.0, 1.05, 1.0) is False
    )
    await db.insert_snapshot(pos, 60, 1.0, position_closed=True)

    assert await _fill_count(db) == 0
    cur = await db.conn.execute("SELECT COUNT(*) AS n FROM snapshots")
    assert int((await cur.fetchone())["n"]) == 0
    # stale id must not resurrect rows after a clean reset
    assert fills_before >= 1
    await db.close()
