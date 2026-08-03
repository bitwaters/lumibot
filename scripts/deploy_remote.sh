#!/usr/bin/env bash
# Pull latest main on the VPS and rebuild the container.
set -euo pipefail

REMOTE_HOST="${LUMIBOT_SSH_HOST:-lumi-server}"
REMOTE_DIR="${LUMIBOT_REMOTE_DIR:-/www/lumibot}"

ssh "$REMOTE_HOST" bash -s <<EOF
set -euo pipefail
cd "$REMOTE_DIR"
if [[ ! -d .git ]]; then
  echo "error: $REMOTE_DIR is not a git checkout; run scripts/setup_server.sh first" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "error: missing $REMOTE_DIR/.env (scp from local)" >&2
  exit 1
fi
mkdir -p data
export GIT_SSH_COMMAND="ssh -i \$HOME/.ssh/lumibot_github_deploy -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
git fetch origin main
git reset --hard origin/main
docker compose up -d --build
docker builder prune -f
docker compose ps
echo "deploy ok: \$(git rev-parse --short HEAD)"
EOF
