#!/usr/bin/env bash
# One-time VPS bootstrap: deploy key, clone into /www/lumibot, data dir.
# Requires: repo already pushed to GitHub; deploy public key added on GitHub.
set -euo pipefail

REMOTE_HOST="${LUMIBOT_SSH_HOST:-lumi-server}"
REMOTE_DIR="${LUMIBOT_REMOTE_DIR:-/www/lumibot}"
REPO_SSH="${LUMIBOT_REPO_SSH:-git@github.com:bitwaters/lumibot.git}"
KEY_PATH="\$HOME/.ssh/lumibot_github_deploy"

echo "==> ensuring deploy key on $REMOTE_HOST"
PUBKEY="$(ssh "$REMOTE_HOST" bash -s <<EOF
set -euo pipefail
mkdir -p "\$HOME/.ssh"
chmod 700 "\$HOME/.ssh"
if [[ ! -f $KEY_PATH ]]; then
  ssh-keygen -t ed25519 -N "" -C "lumibot-readonly-deploy" -f $KEY_PATH
fi
chmod 600 $KEY_PATH
cat ${KEY_PATH}.pub
EOF
)"

echo
echo "Add this Deploy Key (read-only) on GitHub:"
echo "  https://github.com/bitwaters/lumibot/settings/keys"
echo
echo "$PUBKEY"
echo
read -r -p "Press Enter after the deploy key is added on GitHub..."

echo "==> cloning into $REMOTE_DIR"
ssh "$REMOTE_HOST" bash -s <<EOF
set -euo pipefail
export GIT_SSH_COMMAND="ssh -i $KEY_PATH -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
mkdir -p /www
if [[ -d "$REMOTE_DIR/.git" ]]; then
  echo "git checkout already present at $REMOTE_DIR"
elif [[ -d "$REMOTE_DIR" ]] && [[ -n "\$(ls -A '$REMOTE_DIR' 2>/dev/null || true)" ]]; then
  TMP="\$(mktemp -d /www/lumibot-clone.XXXXXX)"
  git clone "$REPO_SSH" "\$TMP"
  # Preserve any existing data/.env
  mkdir -p "$REMOTE_DIR/data"
  shopt -s dotglob nullglob
  for item in "\$TMP"/*; do
    base="\$(basename "\$item")"
    if [[ "\$base" == "data" ]]; then
      continue
    fi
    rm -rf "$REMOTE_DIR/\$base"
    mv "\$item" "$REMOTE_DIR/\$base"
  done
  rm -rf "\$TMP"
else
  mkdir -p "\$(dirname "$REMOTE_DIR")"
  # If empty dir exists, clone into it
  if [[ -d "$REMOTE_DIR" ]]; then
    rmdir "$REMOTE_DIR" 2>/dev/null || true
  fi
  git clone "$REPO_SSH" "$REMOTE_DIR"
fi
mkdir -p "$REMOTE_DIR/data"
echo "checkout: \$(cd "$REMOTE_DIR" && git rev-parse --short HEAD)"
EOF

if [[ -f .env ]]; then
  echo "==> uploading .env"
  scp .env "$REMOTE_HOST:$REMOTE_DIR/.env"
else
  echo "warning: local .env missing; create and scp to $REMOTE_DIR/.env before deploy" >&2
fi

echo
echo "Next:"
echo "  1. Stop any local bot using the same TELEGRAM_BOT_TOKEN"
echo "  2. ./scripts/deploy_remote.sh"
echo "  3. ./scripts/logs_remote.sh"
