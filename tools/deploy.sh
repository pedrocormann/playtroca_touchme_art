#!/usr/bin/env bash
# Sync this repo → Pi at /opt/playtronica and run install_pi.sh.
# Usage: tools/deploy.sh           # full deploy (code + samples)
#        tools/deploy.sh --code    # only code (skip samples — faster)
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${PLAYTRONICA_HOST:-playtronica}"
DST="/opt/playtronica"

CODE_ONLY=0
[[ "${1:-}" == "--code" ]] && CODE_ONLY=1

echo "==> Ensuring destination exists on $HOST"
ssh "$HOST" "sudo mkdir -p $DST && sudo chown -R \$USER:\$USER $DST"

echo "==> Syncing code"
rsync -av --delete \
  --exclude '.git' --exclude '.venv' --exclude 'venv' \
  --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'samples/wav' \
  --exclude 'app/config.json' \
  $( [[ $CODE_ONLY -eq 1 ]] && echo "--exclude samples/sources" ) \
  "$HERE/" "$HOST:$DST/"

echo "==> Running install on Pi"
ssh "$HOST" "bash $DST/tools/install_pi.sh"

echo "==> Restarting service"
ssh "$HOST" "sudo systemctl restart playtronica && sleep 1 && sudo systemctl status playtronica --no-pager | head -15"

echo "==> Done. Web UI: http://$(ssh "$HOST" 'hostname -I' | awk '{print $1}'):8080"
