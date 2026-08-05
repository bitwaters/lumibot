from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import aiosqlite

T = TypeVar("T")


ARCHIVE_TABLES = ("paper_positions", "paper_fills", "snapshots", "alerts")

ARCHIVE_COLUMNS: dict[str, tuple[str, ...]] = {
    "paper_positions": (
        "id", "chain", "token", "symbol", "status", "entry_price", "open_mark",
        "qty", "notional_usd", "cost_basis", "peak_price", "stage1_done",
        "opened_at", "closed_at", "close_reason", "realized_pnl",
    ),
    "paper_fills": (
        "id", "position_id", "side", "price", "qty", "notional_usd", "created_at",
    ),
    "snapshots": (
        "id", "position_id", "offset_sec", "price", "position_closed", "created_at",
    ),
    "alerts": (
        "id", "chain", "token", "source_key", "created_at", "payload_json",
    ),
}


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
  open_mark REAL,
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

CREATE TABLE IF NOT EXISTS paper_skip_opens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chain TEXT NOT NULL,
  token TEXT NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chain TEXT NOT NULL,
  token TEXT NOT NULL,
  source TEXT NOT NULL,
  reason TEXT,
  payload_json TEXT,
  created_at REAL NOT NULL
);

-- Archive tables: /reset_paper moves (not destroys) prior experiment data here,
-- keyed by round_id (auto-increment experiment round), so multi-round analysis
-- stays possible.
CREATE TABLE IF NOT EXISTS rounds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at REAL NOT NULL,
  chain TEXT NOT NULL DEFAULT 'all'
);

CREATE TABLE IF NOT EXISTS paper_positions_archive (
  round_id INTEGER NOT NULL,
  id INTEGER,
  chain TEXT NOT NULL,
  token TEXT NOT NULL,
  symbol TEXT,
  status TEXT NOT NULL,
  entry_price REAL NOT NULL,
  open_mark REAL,
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

CREATE TABLE IF NOT EXISTS paper_fills_archive (
  round_id INTEGER NOT NULL,
  id INTEGER,
  position_id INTEGER NOT NULL,
  side TEXT NOT NULL,
  price REAL NOT NULL,
  qty REAL NOT NULL,
  notional_usd REAL NOT NULL,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS snapshots_archive (
  round_id INTEGER NOT NULL,
  id INTEGER,
  position_id INTEGER NOT NULL,
  offset_sec INTEGER NOT NULL,
  price REAL NOT NULL,
  position_closed INTEGER NOT NULL DEFAULT 0,
  created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts_archive (
  round_id INTEGER NOT NULL,
  id INTEGER,
  chain TEXT NOT NULL,
  token TEXT NOT NULL,
  source_key TEXT NOT NULL,
  created_at REAL NOT NULL,
  payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_pos_archive_round ON paper_positions_archive(round_id, chain);
CREATE INDEX IF NOT EXISTS idx_fills_archive_round ON paper_fills_archive(round_id);
CREATE INDEX IF NOT EXISTS idx_snap_archive_round ON snapshots_archive(round_id);
CREATE INDEX IF NOT EXISTS idx_alerts_archive_round ON alerts_archive(round_id, chain);

CREATE INDEX IF NOT EXISTS idx_cooldowns_token ON cooldowns(chain, token, until_ts);
CREATE INDEX IF NOT EXISTS idx_paper_status ON paper_positions(chain, status);
CREATE INDEX IF NOT EXISTS idx_snapshots_pos ON snapshots(position_id);
CREATE INDEX IF NOT EXISTS idx_signal_log_chain ON signal_log(chain, created_at);
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
        if "open_mark" not in cols:
            await self._conn.execute("ALTER TABLE paper_positions ADD COLUMN open_mark REAL")
        await self._conn.commit()

    async def backfill_open_mark(
        self,
        buy_slip_by_chain: dict[str, float],
        *,
        default_slip: float = 0.05,
    ) -> int:
        """Fill null open_mark from entry_price / (1 + buy_slip). Returns rows updated."""

        async def _tx() -> int:
            cur = await self.conn.execute(
                "SELECT id, chain, entry_price FROM paper_positions WHERE open_mark IS NULL"
            )
            rows = await cur.fetchall()
            n = 0
            for row in rows:
                slip = buy_slip_by_chain.get(row["chain"], default_slip)
                if slip < 0:
                    slip = default_slip
                denom = 1.0 + slip
                if denom <= 0:
                    continue
                open_mark = float(row["entry_price"]) / denom
                await self.conn.execute(
                    "UPDATE paper_positions SET open_mark=? WHERE id=?",
                    (open_mark, row["id"]),
                )
                n += 1
            await self.conn.commit()
            return n

        return await self._with_write(_tx)

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

    async def check_cooldown(
        self,
        chain: str,
        token: str,
        source_key: str,
        same_type_min: int,  # noqa: ARG002 — kept for symmetric signature
        cross_source_min: int,  # noqa: ARG002
    ) -> str | None:
        """Read-only cooldown pre-check (no writes). Returns None if the token is NOT blocked,
        or a reject-reason string ('cooldown_same_type' | 'cooldown_cross_source') if blocked.

        Used as a fast-path gate before expensive API calls.  The result is advisory:
        try_acquire_cooldown must still be called to atomically claim the slot.
        """
        now = time.time()
        cur = await self.conn.execute(
            "SELECT kind FROM cooldowns WHERE chain=? AND token=? AND until_ts>? LIMIT 10",
            (chain, token, now),
        )
        rows = await cur.fetchall()
        for row in rows:
            kind = row["kind"]
            if kind == source_key:
                return "cooldown_same_type"
            if kind == "cross":
                return "cooldown_cross_source"
        return None

    async def try_acquire_cooldown(
        self,
        chain: str,
        token: str,
        source_key: str,
        same_type_min: int,
        cross_source_min: int,
    ) -> str | None:
        """Atomically check+occupy same-type and cross-source cooldowns.
        Returns None if acquired (allowed), or a reject-reason string if blocked.
        """
        now = time.time()
        same_until = now + same_type_min * 60
        cross_until = now + cross_source_min * 60

        async def _tx() -> str | None:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await self.conn.execute(
                    "SELECT kind, until_ts FROM cooldowns WHERE chain=? AND token=? AND until_ts>?",
                    (chain, token, now),
                )
                rows = await cur.fetchall()
                for row in rows:
                    kind = row["kind"]
                    if kind == source_key:
                        await self.conn.commit()
                        return "cooldown_same_type"
                    if kind == "cross":
                        await self.conn.commit()
                        return "cooldown_cross_source"
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
                return None
            except Exception:
                await self.conn.rollback()
                raise

        return await self._with_write(_tx)

    async def has_reentry_block(self, chain: str, token: str) -> str | None:
        """Return 'loss' or 'post_close' if an active re-entry cooldown exists, else None."""
        now = time.time()
        cur = await self.conn.execute(
            """
            SELECT kind FROM cooldowns
            WHERE chain=? AND token=? AND until_ts>? AND kind IN ('loss', 'post_close')
            ORDER BY CASE kind WHEN 'loss' THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (chain, token, now),
        )
        row = await cur.fetchone()
        if not row:
            return None
        return str(row["kind"])

    async def has_symbol_block(self, chain: str, symbol: str) -> bool:
        """True when a position with the same symbol closed recently (symbol_block armed).

        Symbol comparison is case-insensitive: duplicate pumps reuse the same
        name in different casings (e.g. "Daisy" / "DAISY").
        """
        cur = await self.conn.execute(
            "SELECT 1 FROM cooldowns WHERE chain=? AND token=? AND kind='symbol_block' AND until_ts>? LIMIT 1",
            (chain, symbol.lower(), time.time()),
        )
        return await cur.fetchone() is not None

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
        open_mark: float | None = None,
        max_concurrent: int = 0,
    ) -> tuple[int | None, str | None]:
        """Atomic check+open.

        Returns ``(position_id, None)`` on success, or
        ``(None, "already_open"|"max_concurrent")`` when skipped (and records
        a ``paper_skip_opens`` row in both skip cases).
        """
        now = time.time()
        mark = peak_price if open_mark is None else open_mark

        async def _tx() -> tuple[int | None, str | None]:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await self.conn.execute(
                    "SELECT id FROM paper_positions WHERE chain=? AND token=? AND status='open' LIMIT 1",
                    (chain, token),
                )
                existing = await cur.fetchone()
                if existing:
                    await self.conn.execute(
                        "INSERT INTO paper_skip_opens(chain, token, created_at) VALUES(?,?,?)",
                        (chain, token, now),
                    )
                    await self.conn.commit()
                    return None, "already_open"

                if max_concurrent > 0:
                    cur = await self.conn.execute(
                        "SELECT COUNT(*) AS c FROM paper_positions WHERE status='open' AND chain=?",
                        (chain,),
                    )
                    row = await cur.fetchone()
                    open_count = int(row["c"] if row else 0)
                    if open_count >= max_concurrent:
                        await self.conn.execute(
                            "INSERT INTO paper_skip_opens(chain, token, created_at) VALUES(?,?,?)",
                            (chain, token, now),
                        )
                        await self.conn.commit()
                        return None, "max_concurrent"

                cur = await self.conn.execute(
                    """
                    INSERT INTO paper_positions(
                      chain, token, symbol, status, entry_price, open_mark, qty, notional_usd, cost_basis,
                      peak_price, stage1_done, opened_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)
                    """,
                    (
                        chain,
                        token,
                        symbol,
                        "open",
                        entry_price,
                        mark,
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
                return (int(pos_id) if pos_id is not None else None), None
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

    async def count_open_papers(self, chain: str) -> int:
        cur = await self.conn.execute(
            "SELECT COUNT(*) AS c FROM paper_positions WHERE status='open' AND chain=?",
            (chain,),
        )
        row = await cur.fetchone()
        return int(row["c"] if row else 0)

    async def insert_signal_log(
        self, chain: str, token: str, source: str, reason: str | None, payload_json: str | None
    ) -> None:
        async def _tx() -> None:
            await self.conn.execute(
                """
                INSERT INTO signal_log(chain, token, source, reason, payload_json, created_at)
                VALUES(?,?,?,?,?,?)
                """,
                (chain, token, source, reason, payload_json, time.time()),
            )
            await self.conn.commit()

        await self._with_write(_tx)

    async def list_snapshot_targets(self, chain: str, snapshot_count: int) -> list[aiosqlite.Row]:
        """Open positions, plus any closed positions still missing snapshot rows.

        Closed positions are kept until all configured offsets are recorded, so a
        long downtime cannot permanently drop 1m/5m/15m/1h marks.
        """
        cur = await self.conn.execute(
            """
            SELECT p.*, COUNT(s.id) AS snap_count
            FROM paper_positions p
            LEFT JOIN snapshots s ON s.position_id = p.id
            WHERE p.chain=?
            GROUP BY p.id
            HAVING p.status='open' OR snap_count < ?
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
        *,
        loss_cooldown_min: int = 0,
        post_close_cooldown_min: int = 0,
        symbol_cooldown_min: int = 0,
    ) -> bool:
        """Close an open position. Returns False if missing/already closed (e.g. after reset)."""
        now = time.time()

        async def _tx() -> bool:
            cur = await self.conn.execute(
                "SELECT chain, token, symbol FROM paper_positions WHERE id=? AND status='open'",
                (position_id,),
            )
            pos = await cur.fetchone()
            if pos is None:
                return False
            await self.conn.execute(
                """
                UPDATE paper_positions
                SET status='closed', qty=0, closed_at=?, close_reason=?, realized_pnl=realized_pnl+?
                WHERE id=? AND status='open'
                """,
                (now, reason, realized_pnl, position_id),
            )
            await self.conn.execute(
                "INSERT INTO paper_fills(position_id, side, price, qty, notional_usd, created_at) VALUES(?,?,?,?,?,?)",
                (position_id, "sell", price, qty, notional_usd, now),
            )
            chain, token = pos["chain"], pos["token"]
            if post_close_cooldown_min > 0:
                await self.conn.execute(
                    """
                    INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)
                    ON CONFLICT(chain, token, kind) DO UPDATE SET until_ts=excluded.until_ts
                    """,
                    (chain, token, "post_close", now + post_close_cooldown_min * 60),
                )
            if realized_pnl < 0 and loss_cooldown_min > 0:
                await self.conn.execute(
                    """
                    INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)
                    ON CONFLICT(chain, token, kind) DO UPDATE SET until_ts=excluded.until_ts
                    """,
                    (chain, token, "loss", now + loss_cooldown_min * 60),
                )
            symbol = pos["symbol"] if "symbol" in pos.keys() else None
            if symbol and symbol_cooldown_min > 0:
                await self.conn.execute(
                    """
                    INSERT INTO cooldowns(chain, token, kind, until_ts) VALUES(?,?,?,?)
                    ON CONFLICT(chain, token, kind) DO UPDATE SET until_ts=excluded.until_ts
                    """,
                    (chain, symbol.lower(), "symbol_block", now + symbol_cooldown_min * 60),
                )
            await self.conn.commit()
            return True

        return await self._with_write(_tx)

    async def abort_paper_open(self, position_id: int) -> None:
        """Void a just-opened position without arming loss/post_close cooldowns."""

        async def _tx() -> None:
            await self.conn.execute("DELETE FROM paper_fills WHERE position_id=?", (position_id,))
            await self.conn.execute("DELETE FROM snapshots WHERE position_id=?", (position_id,))
            await self.conn.execute(
                "DELETE FROM paper_positions WHERE id=? AND status='open'",
                (position_id,),
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
    ) -> bool:
        """Stage1 partial sell. Returns False if position missing/not open."""
        now = time.time()

        async def _tx() -> bool:
            cur = await self.conn.execute(
                "SELECT id FROM paper_positions WHERE id=? AND status='open'",
                (position_id,),
            )
            if await cur.fetchone() is None:
                return False
            await self.conn.execute(
                """
                UPDATE paper_positions
                SET qty=?, cost_basis=?, stage1_done=1, realized_pnl=realized_pnl+?
                WHERE id=? AND status='open'
                """,
                (remaining_qty, new_cost_basis, realized_pnl, position_id),
            )
            await self.conn.execute(
                "INSERT INTO paper_fills(position_id, side, price, qty, notional_usd, created_at) VALUES(?,?,?,?,?,?)",
                (position_id, "sell", price, qty, notional_usd, now),
            )
            await self.conn.commit()
            return True

        return await self._with_write(_tx)

    async def insert_snapshot(
        self, position_id: int, offset_sec: int, price: float, position_closed: bool
    ) -> None:
        async def _tx() -> None:
            cur = await self.conn.execute(
                "SELECT id FROM paper_positions WHERE id=?",
                (position_id,),
            )
            if await cur.fetchone() is None:
                return
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

    async def list_recent_closed_papers(
        self, limit: int = 10, chain: str | None = None
    ) -> list[aiosqlite.Row]:
        if chain:
            cur = await self.conn.execute(
                """
                SELECT * FROM paper_positions
                WHERE status='closed' AND chain=?
                ORDER BY closed_at DESC
                LIMIT ?
                """,
                (chain, limit),
            )
        else:
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

    async def paper_stats_summary(self, chain: str | None = None) -> dict[str, Any]:
        """Current-experiment stats from paper tables only (not alerts). Optionally filtered by chain."""
        where = "WHERE chain=?" if chain else ""
        params: tuple[Any, ...] = (chain,) if chain else ()
        cur = await self.conn.execute(
            f"""
            SELECT
              COALESCE(SUM(CASE WHEN status='open' THEN 1 ELSE 0 END), 0) AS open_count,
              COALESCE(SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END), 0) AS closed_count,
              COALESCE(SUM(CASE WHEN status='closed' THEN realized_pnl ELSE 0 END), 0) AS closed_pnl,
              COALESCE(SUM(CASE WHEN status='open' THEN notional_usd ELSE 0 END), 0) AS open_notional,
              COALESCE(COUNT(*), 0) AS opened_count,
              COALESCE(SUM(CASE WHEN status='closed' AND close_reason='hard_stop' THEN 1 ELSE 0 END), 0)
                AS hard_stop_count,
              COALESCE(SUM(CASE WHEN status='closed' AND realized_pnl > 0 THEN 1 ELSE 0 END), 0)
                AS win_count,
              AVG(CASE WHEN status='closed' AND realized_pnl > 0 THEN realized_pnl END)
                AS avg_win_usd,
              AVG(CASE WHEN status='closed' AND realized_pnl <= 0 THEN realized_pnl END)
                AS avg_loss_usd,
              AVG(CASE WHEN status='closed' AND closed_at IS NOT NULL
                       THEN (closed_at - opened_at) END)
                AS avg_hold_sec
            FROM paper_positions
            {where}
            """,
            params,
        )
        row = await cur.fetchone()
        skip_where = "WHERE chain=?" if chain else ""
        skip_cur = await self.conn.execute(
            f"SELECT COALESCE(COUNT(*), 0) AS skipped_open_count FROM paper_skip_opens {skip_where}",
            params,
        )
        skip_row = await skip_cur.fetchone()
        closed = int(row["closed_count"] if row else 0)
        win_count = int(row["win_count"] if row and row["win_count"] is not None else 0)
        return {
            "open_count": int(row["open_count"] if row else 0),
            "closed_count": closed,
            "closed_pnl": float(row["closed_pnl"] if row else 0),
            "open_notional": float(row["open_notional"] if row else 0),
            "opened_count": int(row["opened_count"] if row else 0),
            "skipped_open_count": int(skip_row["skipped_open_count"] if skip_row else 0),
            "hard_stop_count": int(row["hard_stop_count"] if row else 0),
            "win_count": win_count,
            "win_rate": (win_count / closed) if closed > 0 else None,
            "avg_win_usd": float(row["avg_win_usd"]) if row and row["avg_win_usd"] is not None else None,
            "avg_loss_usd": float(row["avg_loss_usd"]) if row and row["avg_loss_usd"] is not None else None,
            "avg_hold_sec": float(row["avg_hold_sec"]) if row and row["avg_hold_sec"] is not None else None,
        }

    async def reset_paper_experiment(self, chain: str = "all") -> dict[str, int]:
        """Clear paper state for a fresh simulation cohort, archiving the old one.

        chain="all" clears every chain (legacy full-table behaviour). Any other value
        scopes the delete to that chain only, using position_id subqueries for the
        two tables (paper_fills, snapshots) that have no chain column of their own.

        Archived rows are copied into the *_archive tables under a round_id (an
        auto-increment round serial) BEFORE being deleted, so earlier cohorts stay
        analyzable via /rounds or direct SQL on the archive tables. signal_log is
        never touched.
        """
        round_id: int | None = None

        async def _run() -> dict[str, int]:
            nonlocal round_id
            out: dict[str, int] = {"round_id": 0}
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                cur = await self.conn.execute(
                    "INSERT INTO rounds(created_at, chain) VALUES(?,?)",
                    (time.time(), chain),
                )
                round_id = int(cur.lastrowid or 0)
                out["round_id"] = round_id
                if chain == "all":
                    for table in ARCHIVE_TABLES:
                        await self._archive_table(table, round_id)
                    for table in ARCHIVE_TABLES + (
                        "paper_skip_opens",
                        "cooldowns",
                        "reject_counts",
                    ):
                        cur = await self.conn.execute(f"DELETE FROM {table}")
                        out[table] = int(cur.rowcount or 0)
                else:
                    cur = await self.conn.execute(
                        "SELECT id FROM paper_positions WHERE chain=?", (chain,)
                    )
                    pos_ids = [r["id"] for r in await cur.fetchall()]
                    await self._archive_table("paper_positions", round_id, "chain=?", (chain,))
                    if pos_ids:
                        marks = ",".join("?" * len(pos_ids))
                        await self._archive_table(
                            "paper_fills", round_id, f"position_id IN ({marks})", pos_ids
                        )
                        await self._archive_table(
                            "snapshots", round_id, f"position_id IN ({marks})", pos_ids
                        )
                    await self._archive_table("alerts", round_id, "chain=?", (chain,))
                    for table in ("paper_positions", "paper_skip_opens", "cooldowns", "alerts", "reject_counts"):
                        cur = await self.conn.execute(f"DELETE FROM {table} WHERE chain=?", (chain,))
                        out[table] = int(cur.rowcount or 0)
                    if pos_ids:
                        marks = ",".join("?" * len(pos_ids))
                        for table in ("paper_fills", "snapshots"):
                            cur = await self.conn.execute(
                                f"DELETE FROM {table} WHERE position_id IN ({marks})", pos_ids
                            )
                            out[table] = int(cur.rowcount or 0)
                    else:
                        out["paper_fills"] = 0
                        out["snapshots"] = 0
                await self.conn.commit()
            except Exception:
                await self.conn.rollback()
                raise
            return out

        return await self._with_write(_run)

    async def _archive_table(
        self,
        table: str,
        round_id: int,
        where_sql: str | None = None,
        params: tuple | list = (),
    ) -> int:
        """Copy rows from a live table into its *_archive table with a round_id tag.

        Runs inside the caller's transaction; must be invoked within reset's
        BEGIN IMMEDIATE block.
        """
        cols = ARCHIVE_COLUMNS[table]
        col_list = ", ".join(cols)
        sql = (
            f"INSERT INTO {table}_archive (round_id, {col_list}) "
            f"SELECT {round_id}, {col_list} FROM {table}"
        )
        if where_sql:
            sql += f" WHERE {where_sql}"
        cur = await self.conn.execute(sql, params)
        return int(cur.rowcount or 0)

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

    async def list_recent_alerts(
        self, limit: int = 10, chain: str | None = None
    ) -> list[aiosqlite.Row]:
        if chain:
            cur = await self.conn.execute(
                """
                SELECT chain, token, source_key, created_at, payload_json
                FROM alerts
                WHERE chain=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (chain, limit),
            )
        else:
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

    async def count_active_cooldowns(self, chain: str | None = None) -> int:
        now = time.time()
        if chain:
            cur = await self.conn.execute(
                "SELECT COUNT(*) AS c FROM cooldowns WHERE until_ts>? AND chain=?",
                (now, chain),
            )
        else:
            cur = await self.conn.execute(
                "SELECT COUNT(*) AS c FROM cooldowns WHERE until_ts>?",
                (now,),
            )
        row = await cur.fetchone()
        return int(row["c"] if row else 0)

    async def list_archive_rounds(self, limit: int = 20) -> list[aiosqlite.Row]:
        """Archived experiment rounds, newest first, with cohort summaries."""
        cur = await self.conn.execute(
            """
            SELECT
              a.round_id,
              r.chain AS reset_chain,
              r.created_at AS reset_at,
              COUNT(*) AS positions,
              COALESCE(SUM(CASE WHEN a.status='closed' THEN 1 ELSE 0 END), 0) AS closed_count,
              COALESCE(SUM(CASE WHEN a.status='open' THEN 1 ELSE 0 END), 0) AS open_count,
              COALESCE(SUM(CASE WHEN a.status='closed' THEN a.realized_pnl ELSE 0 END), 0)
                AS closed_pnl
            FROM paper_positions_archive a
            JOIN rounds r ON r.id = a.round_id
            GROUP BY a.round_id
            ORDER BY a.round_id DESC
            LIMIT ?
            """,
            (max(0, limit),),
        )
        return list(await cur.fetchall())

    async def archive_round_stats(
        self, round_id: int, chain: str | None = None
    ) -> dict[str, Any]:
        """Per-round summary from the archive tables (mirrors paper_stats_summary)."""
        where = "AND chain=?" if chain else ""
        params: tuple[Any, ...] = (round_id,) + ((chain,) if chain else ())
        cur = await self.conn.execute(
            f"""
            SELECT
              COALESCE(SUM(CASE WHEN status='open' THEN 1 ELSE 0 END), 0) AS open_count,
              COALESCE(SUM(CASE WHEN status='closed' THEN 1 ELSE 0 END), 0) AS closed_count,
              COALESCE(SUM(CASE WHEN status='closed' THEN realized_pnl ELSE 0 END), 0)
                AS closed_pnl,
              COALESCE(SUM(CASE WHEN status='closed' AND realized_pnl > 0 THEN 1 ELSE 0 END), 0)
                AS win_count,
              COALESCE(SUM(CASE WHEN status='closed' AND close_reason='hard_stop' THEN 1 ELSE 0 END), 0)
                AS hard_stop_count,
              AVG(CASE WHEN status='closed' AND realized_pnl > 0 THEN realized_pnl END)
                AS avg_win_usd,
              AVG(CASE WHEN status='closed' AND realized_pnl <= 0 THEN realized_pnl END)
                AS avg_loss_usd
            FROM paper_positions_archive
            WHERE round_id=? {where}
            """,
            params,
        )
        row = await cur.fetchone()
        closed = int(row["closed_count"] if row else 0)
        win_count = int(row["win_count"] if row and row["win_count"] is not None else 0)
        return {
            "round_id": round_id,
            "chain": chain,
            "open_count": int(row["open_count"] if row else 0),
            "closed_count": closed,
            "closed_pnl": float(row["closed_pnl"] if row else 0),
            "win_count": win_count,
            "win_rate": (win_count / closed) if closed > 0 else None,
            "hard_stop_count": int(row["hard_stop_count"] if row else 0),
            "avg_win_usd": float(row["avg_win_usd"]) if row and row["avg_win_usd"] is not None else None,
            "avg_loss_usd": float(row["avg_loss_usd"]) if row and row["avg_loss_usd"] is not None else None,
        }

    async def list_archive_closed_papers(
        self, round_id: int, limit: int = 5, chain: str | None = None
    ) -> list[aiosqlite.Row]:
        where = "AND chain=?" if chain else ""
        params: tuple[Any, ...] = (round_id,) + ((chain,) if chain else ()) + (max(0, limit),)
        cur = await self.conn.execute(
            f"""
            SELECT * FROM paper_positions_archive
            WHERE round_id=? {where} AND status='closed'
            ORDER BY closed_at DESC
            LIMIT ?
            """,
            params,
        )
        return list(await cur.fetchall())
