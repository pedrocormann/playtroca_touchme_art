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
# Main sync — code, scripts, samples/sources.
# We DO NOT --delete inside app/presets/ because presets are user data created
# on the Pi via the UI; deleting them on every deploy would wipe them out.
# Instead we ship local *.json presets up (via the second pass below) but leave
# Pi-only presets intact.
rsync -av --delete \
  --exclude '.git' --exclude '.venv' --exclude 'venv' \
  --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'samples/wav' \
  --exclude 'app/config.json' \
  --exclude 'app/presets/' \
  $( [[ $CODE_ONLY -eq 1 ]] && echo "--exclude samples/sources" ) \
  "$HERE/" "$HOST:$DST/"

# Second pass: push only the *.json presets we have locally to the Pi, never
# delete on the Pi side. Files unique to the Pi survive untouched.
mkdir -p "$HERE/app/presets"
if compgen -G "$HERE/app/presets/*.json" > /dev/null; then
  rsync -av "$HERE/app/presets/"*.json "$HOST:$DST/app/presets/"
fi

echo "==> Running install on Pi"
ssh "$HOST" "bash $DST/tools/install_pi.sh"

echo "==> Restarting service"
ssh "$HOST" "sudo systemctl restart playtronica && sleep 1 && sudo systemctl status playtronica --no-pager | head -15"

echo "==> Done. Web UI: http://$(ssh "$HOST" 'hostname -I' | awk '{print $1}'):8080"
