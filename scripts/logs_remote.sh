#!/usr/bin/env bash
# Stream container logs from the VPS.
set -euo pipefail

REMOTE_HOST="${LUMIBOT_SSH_HOST:-lumi-server}"
REMOTE_DIR="${LUMIBOT_REMOTE_DIR:-/www/lumibot}"
TAIL="${1:-200}"

ssh -t "$REMOTE_HOST" "cd '$REMOTE_DIR' && docker compose logs -f --tail='$TAIL'"
