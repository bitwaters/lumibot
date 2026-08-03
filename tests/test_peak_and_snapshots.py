import time

import pytest

from lumibot.db import Database
from lumibot.strategy import StrategyOrder


@pytest.mark.asyncio
async def test_open_paper_stores_mark_peak(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    mark = 1.0
    entry = StrategyOrder.buy_fill_price(mark, 0.05)
    pos_id = await db.try_open_paper("sol", "tok", entry, 20 / entry, 20.0, peak_price=mark)
    assert pos_id is not None
    row = await db.get_open_paper("sol", "tok")
    assert row is not None
    assert row["peak_price"] == mark
    assert row["entry_price"] == entry
    await db.close()


@pytest.mark.asyncio
async def test_closed_position_still_gets_due_snapshots(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    opened = time.time() - 120
    cur = await db.conn.execute(
        """
        INSERT INTO paper_positions(
          chain, token, status, entry_price, qty, notional_usd, cost_basis,
          peak_price, stage1_done, opened_at, closed_at, close_reason
        ) VALUES(?,?,?,?,?,?,?,?,0,?,?,?)
        """,
        ("sol", "tok", "closed", 1.0, 0, 20, 1.0, 1.0, opened, time.time(), "hard_stop"),
    )
    await db.conn.commit()
    pos_id = cur.lastrowid
    missing = await db.missing_snapshot_offsets(pos_id, [60, 300])
    assert missing == [60, 300]
    await db.insert_snapshot(pos_id, 60, 0.9, True)
    missing2 = await db.missing_snapshot_offsets(pos_id, [60, 300])
    assert missing2 == [300]
    cur = await db.conn.execute("SELECT position_closed FROM snapshots WHERE position_id=? AND offset_sec=60", (pos_id,))
    row = await cur.fetchone()
    assert row["position_closed"] == 1
    await db.close()


@pytest.mark.asyncio
async def test_release_cooldown_allows_retry(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    assert await db.try_acquire_cooldown("sol", "tok", "signal:12", 45, 15)
    await db.release_cooldown("sol", "tok", "signal:12")
    assert await db.try_acquire_cooldown("sol", "tok", "signal:12", 45, 15)
    await db.close()


@pytest.mark.asyncio
async def test_release_cooldown_does_not_clear_other_source_cross(tmp_path):
    db = Database(str(tmp_path / "t.db"))
    await db.connect()
    # Simulate stale A rows + active B ownership of cross.
    now = time.time()
    await db.conn.execute(
        "INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)",
        ("sol", "tok", "signal:12", now + 1000),
    )
    await db.conn.execute(
        "INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)",
        ("sol", "tok", "trending", now + 1000),
    )
    await db.conn.execute(
        "INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)",
        ("sol", "tok", "cross", now + 1000),
    )
    await db.conn.commit()
    await db.release_cooldown("sol", "tok", "signal:12")
    cur = await db.conn.execute(
        "SELECT kind FROM cooldowns WHERE chain=? AND token=? ORDER BY kind",
        ("sol", "tok"),
    )
    kinds = [r["kind"] for r in await cur.fetchall()]
    assert kinds == ["cross", "trending"]
    await db.close()
