#!/usr/bin/env bash
# Clear paper experiment tables on the VPS (same scope as TG /reset_paper).
#
# Usage:
#   ./scripts/reset_paper_remote.sh              # all chains (default)
#   CHAIN=sol ./scripts/reset_paper_remote.sh    # one chain: sol|bsc|robinhood|all
set -euo pipefail

REMOTE_HOST="${LUMIBOT_SSH_HOST:-lumi-server}"
REMOTE_DIR="${LUMIBOT_REMOTE_DIR:-/www/lumibot}"
CHAIN="${CHAIN:-all}"

case "$CHAIN" in
  sol|bsc|robinhood|all) ;;
  *)
    echo "CHAIN must be sol|bsc|robinhood|all, got: $CHAIN" >&2
    exit 1
    ;;
esac

ssh "$REMOTE_HOST" bash -s -- "$REMOTE_DIR" "$CHAIN" <<'EOF'
set -euo pipefail
REMOTE_DIR="$1"
CHAIN="$2"
cd "$REMOTE_DIR"
docker compose stop lumibot
python3 - <<PY
import sqlite3
chain = "$CHAIN"
con = sqlite3.connect("$REMOTE_DIR/data/lumibot.db")
cur = con.cursor()
tables_with_chain = (
    "paper_positions",
    "paper_skip_opens",
    "cooldowns",
    "alerts",
    "reject_counts",
)
try:
    cur.execute("BEGIN IMMEDIATE")
    if chain == "all":
        for t in ("paper_fills", "snapshots", *tables_with_chain):
            cur.execute(f"DELETE FROM {t}")
            print(t, "deleted", cur.rowcount)
    else:
        cur.execute(
            "DELETE FROM paper_fills WHERE position_id IN "
            "(SELECT id FROM paper_positions WHERE chain=?)",
            (chain,),
        )
        print("paper_fills", "deleted", cur.rowcount)
        cur.execute(
            "DELETE FROM snapshots WHERE position_id IN "
            "(SELECT id FROM paper_positions WHERE chain=?)",
            (chain,),
        )
        print("snapshots", "deleted", cur.rowcount)
        for t in tables_with_chain:
            cur.execute(f"DELETE FROM {t} WHERE chain=?", (chain,))
            print(t, "deleted", cur.rowcount)
    con.commit()
except Exception:
    con.rollback()
    raise
cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
con.close()
print("paper reset ok chain=", chain)
PY
docker compose up -d
docker compose ps
EOF
