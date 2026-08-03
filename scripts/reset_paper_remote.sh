#!/usr/bin/env bash
# Clear paper experiment tables on the VPS (same scope as /reset_paper confirm).
set -euo pipefail

REMOTE_HOST="${LUMIBOT_SSH_HOST:-lumi-server}"
REMOTE_DIR="${LUMIBOT_REMOTE_DIR:-/www/lumibot}"

ssh "$REMOTE_HOST" bash -s <<EOF
set -euo pipefail
cd "$REMOTE_DIR"
docker compose stop lumibot
python3 - <<'PY'
import sqlite3
con = sqlite3.connect("$REMOTE_DIR/data/lumibot.db")
cur = con.cursor()
tables = (
    "paper_fills",
    "snapshots",
    "paper_positions",
    "paper_skip_opens",
    "cooldowns",
    "alerts",
    "reject_counts",
)
try:
    cur.execute("BEGIN IMMEDIATE")
    for t in tables:
        cur.execute(f"DELETE FROM {t}")
        print(t, "deleted", cur.rowcount)
    con.commit()
except Exception:
    con.rollback()
    raise
cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
con.close()
print("paper reset ok")
PY
docker compose up -d
docker compose ps
EOF
