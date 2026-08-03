from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import aiosqlite

T = TypeVar("T")


SCHEMA = """
CREATE TABLE IF NOT EXISTS cooldowns (
  chain TEXT NOT NULL,
  token TEXT NOT NULL,
  kind TEXT NOT NULL,
  until_ts REAL NOT NULL,
  PRIMARY KEY (chain, token, kind)
);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chain TEXT NOT NULL,
  token TEXT NOT NULL,
  source_key TEXT NOT NULL,
  created_at REAL NOT NULL,
  payload_json TEXT
);

CREATE TABLE IF NOT EXISTS paper_positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chain TEXT NOT NULL,
  token TEXT NOT NULL,
  symbol TEXT,
  status TEXT NOT NULL,
  entry_price REAL NOT NULL,
  qty REAL NOT NULL,
  notional_usd REAL NOT NULL,
  cost_basis REAL NOT NULL,
  peak_price REAL NOT NULL,
  stage1_done INTEGER NOT NULL DEFAULT 0,
  opened_at REAL NOT NULL,
  closed_at REAL,
  close_reason TEXT,
  realized_pnl REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS paper_fills (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  position_id INTEGER NOT NULL,
  side TEXT NOT NULL,
  price REAL NOT NULL,
  qty REAL NOT NULL,
  notional_usd REAL NOT NULL,
  created_at REAL NOT NULL,
  FOREIGN KEY(position_id) REFERENCES paper_positions(id)
);

CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  position_id INTEGER NOT NULL,
  offset_sec INTEGER NOT NULL,
  price REAL NOT NULL,
  position_closed INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  UNIQUE(position_id, offset_sec),
  FOREIGN KEY(position_id) REFERENCES paper_positions(id)
);

CREATE TABLE IF NOT EXISTS daily_stats (
  chain TEXT NOT NULL,
  day_utc TEXT NOT NULL,
  live_realized_pnl REAL NOT NULL DEFAULT 0,
  live_trades INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (chain, day_utc)
);

CREATE TABLE IF NOT EXISTS reject_counts (
  chain TEXT NOT NULL,
  source TEXT NOT NULL,
  reason TEXT NOT NULL,
  count INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (chain, source, reason)
);
"""


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    async def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.executescript(SCHEMA)
        # Lightweight migrations for existing DBs
        info_rows = await (await self._conn.execute("PRAGMA table_info(paper_positions)")).fetchall()
        cols = {r["name"] for r in info_rows}
        if "symbol" not in cols:
            await self._conn.execute("ALTER TABLE paper_positions ADD COLUMN symbol TEXT")
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("database not connected")
        return self._conn

    async def _with_write(self, fn: Callable[[], Awaitable[T]]) -> T:
        async with self._write_lock:
            return await fn()

    async def try_acquire_cooldown(
        self,
        chain: str,
        token: str,
        source_key: str,
        same_type_min: int,
        cross_source_min: int,
    ) -> bool:
        """Atomically check+occupy same-type and cross-source cooldowns. True if allowed."""
        now = time.time()
        same_until = now + same_type_min * 60
        cross_until = now + cross_source_min * 60

        async def _tx() -> bool:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await self.conn.execute(
                    "SELECT kind, until_ts FROM cooldowns WHERE chain=? AND token=? AND until_ts>?",
                    (chain, token, now),
                )
                rows = await cur.fetchall()
                for row in rows:
                    kind = row["kind"]
                    if kind == source_key or kind == "cross":
                        await self.conn.commit()
                        return False
                await self.conn.execute(
                    """
                    INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)
                    ON CONFLICT(chain, token, kind) DO UPDATE SET until_ts=excluded.until_ts
                    """,
                    (chain, token, source_key, same_until),
                )
                await self.conn.execute(
                    """
                    INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)
                    ON CONFLICT(chain, token, kind) DO UPDATE SET until_ts=excluded.until_ts
                    """,
                    (chain, token, "cross", cross_until),
                )
                await self.conn.commit()
                return True
            except Exception:
                await self.conn.rollback()
                raise

        return await self._with_write(_tx)

    async def release_cooldown(self, chain: str, token: str, source_key: str) -> None:
        """Rollback a just-acquired cooldown after notify failure.

        Only delete `cross` when this source_key row existed and no other
        non-cross cooldown remains for the token (avoids clearing another source).
        """

        async def _tx() -> None:
            cur = await self.conn.execute(
                "DELETE FROM cooldowns WHERE chain=? AND token=? AND kind=?",
                (chain, token, source_key),
            )
            if cur.rowcount and cur.rowcount > 0:
                cur2 = await self.conn.execute(
                    """
                    SELECT 1 FROM cooldowns
                    WHERE chain=? AND token=? AND kind!='cross' AND until_ts>?
                    LIMIT 1
                    """,
                    (chain, token, time.time()),
                )
                if await cur2.fetchone() is None:
                    await self.conn.execute(
                        "DELETE FROM cooldowns WHERE chain=? AND token=? AND kind='cross'",
                        (chain, token),
                    )
            await self.conn.commit()

        await self._with_write(_tx)

    async def insert_alert(self, chain: str, token: str, source_key: str, payload_json: str) -> None:
        async def _tx() -> None:
            await self.conn.execute(
                "INSERT INTO alerts(chain, token, source_key, created_at, payload_json) VALUES(?,?,?,?,?)",
                (chain, token, source_key, time.time(), payload_json),
            )
            await self.conn.commit()

        await self._with_write(_tx)

    async def bump_reject(self, chain: str, source: str, reason: str) -> None:
        async def _tx() -> None:
            await self.conn.execute(
                """
                INSERT INTO reject_counts(chain, source, reason, count) VALUES(?,?,?,1)
                ON CONFLICT(chain, source, reason) DO UPDATE SET count=count+1
                """,
                (chain, source, reason),
            )
            await self.conn.commit()

        await self._with_write(_tx)

    async def get_open_paper(self, chain: str, token: str) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT * FROM paper_positions WHERE chain=? AND token=? AND status='open' LIMIT 1",
            (chain, token),
        )
        return await cur.fetchone()

    async def try_open_paper(
        self,
        chain: str,
        token: str,
        entry_price: float,
        qty: float,
        notional_usd: float,
        peak_price: float,
        symbol: str | None = None,
    ) -> int | None:
        """Atomic check+open. Returns position id or None if already open."""
        now = time.time()

        async def _tx() -> int | None:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await self.conn.execute(
                    "SELECT id FROM paper_positions WHERE chain=? AND token=? AND status='open' LIMIT 1",
                    (chain, token),
                )
                existing = await cur.fetchone()
                if existing:
                    await self.conn.commit()
                    return None
                cur = await self.conn.execute(
                    """
                    INSERT INTO paper_positions(
                      chain, token, symbol, status, entry_price, qty, notional_usd, cost_basis,
                      peak_price, stage1_done, opened_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,0,?)
                    """,
                    (
                        chain,
                        token,
                        symbol,
                        "open",
                        entry_price,
                        qty,
                        notional_usd,
                        entry_price,
                        peak_price,
                        now,
                    ),
                )
                pos_id = cur.lastrowid
                await self.conn.execute(
                    "INSERT INTO paper_fills(position_id, side, price, qty, notional_usd, created_at) VALUES(?,?,?,?,?,?)",
                    (pos_id, "buy", entry_price, qty, notional_usd, now),
                )
                await self.conn.commit()
                return int(pos_id) if pos_id is not None else None
            except Exception:
                await self.conn.rollback()
                raise

        return await self._with_write(_tx)

    async def list_open_papers(self, chain: str | None = None) -> list[aiosqlite.Row]:
        if chain:
            cur = await self.conn.execute(
                "SELECT * FROM paper_positions WHERE status='open' AND chain=?",
                (chain,),
            )
        else:
            cur = await self.conn.execute("SELECT * FROM paper_positions WHERE status='open'")
        return list(await cur.fetchall())

    async def list_snapshot_targets(self, chain: str, snapshot_count: int) -> list[aiosqlite.Row]:
        """Open positions, plus any closed positions still missing snapshot rows.

        Closed positions are kept until all configured offsets are recorded, so a
        long downtime cannot permanently drop 1m/5m/15m/1h marks.
        """
        cur = await self.conn.execute(
            """
            SELECT p.* FROM paper_positions p
            WHERE p.chain=?
              AND (
                p.status='open'
                OR (
                  p.status='closed'
                  AND (
                    SELECT COUNT(*) FROM snapshots s WHERE s.position_id=p.id
                  ) < ?
                )
              )
            ORDER BY p.id
            """,
            (chain, max(0, snapshot_count)),
        )
        return list(await cur.fetchall())

    async def missing_snapshot_offsets(self, position_id: int, offsets: list[int]) -> list[int]:
        if not offsets:
            return []
        cur = await self.conn.execute(
            "SELECT offset_sec FROM snapshots WHERE position_id=?",
            (position_id,),
        )
        have = {int(r["offset_sec"]) for r in await cur.fetchall()}
        return [o for o in offsets if o not in have]

    async def update_paper_mark(
        self,
        position_id: int,
        *,
        qty: float | None = None,
        cost_basis: float | None = None,
        peak_price: float | None = None,
        stage1_done: int | None = None,
    ) -> None:
        fields: list[str] = []
        vals: list[Any] = []
        if qty is not None:
            fields.append("qty=?")
            vals.append(qty)
        if cost_basis is not None:
            fields.append("cost_basis=?")
            vals.append(cost_basis)
        if peak_price is not None:
            fields.append("peak_price=?")
            vals.append(peak_price)
        if stage1_done is not None:
            fields.append("stage1_done=?")
            vals.append(stage1_done)
        if not fields:
            return
        vals.append(position_id)

        async def _tx() -> None:
            await self.conn.execute(
                f"UPDATE paper_positions SET {', '.join(fields)} WHERE id=?",
                vals,
            )
            await self.conn.commit()

        await self._with_write(_tx)

    async def close_paper(
        self,
        position_id: int,
        price: float,
        qty: float,
        notional_usd: float,
        reason: str,
        realized_pnl: float,
    ) -> None:
        now = time.time()

        async def _tx() -> None:
            await self.conn.execute(
                """
                UPDATE paper_positions
                SET status='closed', qty=0, closed_at=?, close_reason=?, realized_pnl=realized_pnl+?
                WHERE id=?
                """,
                (now, reason, realized_pnl, position_id),
            )
            await self.conn.execute(
                "INSERT INTO paper_fills(position_id, side, price, qty, notional_usd, created_at) VALUES(?,?,?,?,?,?)",
                (position_id, "sell", price, qty, notional_usd, now),
            )
            await self.conn.commit()

        await self._with_write(_tx)

    async def add_partial_sell(
        self,
        position_id: int,
        price: float,
        qty: float,
        notional_usd: float,
        remaining_qty: float,
        new_cost_basis: float,
        realized_pnl: float,
    ) -> None:
        now = time.time()

        async def _tx() -> None:
            await self.conn.execute(
                """
                UPDATE paper_positions
                SET qty=?, cost_basis=?, stage1_done=1, realized_pnl=realized_pnl+?
                WHERE id=?
                """,
                (remaining_qty, new_cost_basis, realized_pnl, position_id),
            )
            await self.conn.execute(
                "INSERT INTO paper_fills(position_id, side, price, qty, notional_usd, created_at) VALUES(?,?,?,?,?,?)",
                (position_id, "sell", price, qty, notional_usd, now),
            )
            await self.conn.commit()

        await self._with_write(_tx)

    async def insert_snapshot(
        self, position_id: int, offset_sec: int, price: float, position_closed: bool
    ) -> None:
        async def _tx() -> None:
            await self.conn.execute(
                """
                INSERT OR IGNORE INTO snapshots(position_id, offset_sec, price, position_closed, created_at)
                VALUES(?,?,?,?,?)
                """,
                (position_id, offset_sec, price, 1 if position_closed else 0, time.time()),
            )
            await self.conn.commit()

        await self._with_write(_tx)

    async def get_live_daily(self, chain: str, day_utc: str) -> aiosqlite.Row | None:
        cur = await self.conn.execute(
            "SELECT * FROM daily_stats WHERE chain=? AND day_utc=?",
            (chain, day_utc),
        )
        return await cur.fetchone()

    async def list_recent_closed_papers(self, limit: int = 10) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT * FROM paper_positions
            WHERE status='closed'
            ORDER BY closed_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return list(await cur.fetchall())

    async def paper_stats_summary(self) -> dict[str, Any]:
        cur = await self.conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN status='open' THEN 1 ELSE 0 END), 0) AS open_count,
              COALESCE(SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END), 0) AS closed_count,
              COALESCE(SUM(CASE WHEN status='closed' THEN realized_pnl ELSE 0 END), 0) AS closed_pnl,
              COALESCE(SUM(CASE WHEN status='open' THEN notional_usd ELSE 0 END), 0) AS open_notional
            FROM paper_positions
            """
        )
        row = await cur.fetchone()
        if not row:
            return {
                "open_count": 0,
                "closed_count": 0,
                "closed_pnl": 0.0,
                "open_notional": 0.0,
            }
        return {
            "open_count": int(row["open_count"] or 0),
            "closed_count": int(row["closed_count"] or 0),
            "closed_pnl": float(row["closed_pnl"] or 0),
            "open_notional": float(row["open_notional"] or 0),
        }

    async def top_reject_reasons(self, limit: int = 15) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT chain, source, reason, count
            FROM reject_counts
            ORDER BY count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return list(await cur.fetchall())

    async def list_recent_alerts(self, limit: int = 10) -> list[aiosqlite.Row]:
        cur = await self.conn.execute(
            """
            SELECT chain, token, source_key, created_at, payload_json
            FROM alerts
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        return list(await cur.fetchall())

    async def count_active_cooldowns(self) -> int:
        now = time.time()
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS c FROM cooldowns WHERE until_ts>?",
            (now,),
        )
        row = await cur.fetchone()
        return int(row["c"] if row else 0)
