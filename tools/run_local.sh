#!/usr/bin/env bash
# Run the Flask UI locally on the Mac as a "playground" for tuning presets.
# - Creates a virtualenv at .venv/ on first run
# - Installs Flask + mido + python-rtmidi + pygame inside it
# - Builds samples/wav/ from samples/sources/ if missing
# - Starts the same Flask UI on http://127.0.0.1:8080
#
# Presets are written to app/presets/, which is the same path the Pi uses;
# running `tools/deploy.sh` afterwards pushes them to the Pi unchanged.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

if [[ ! -d .venv ]]; then
  echo "==> creating virtualenv at .venv/"
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

if [[ ! -f .venv/.deps-installed ]]; then
  echo "==> installing Python deps (Flask, mido, python-rtmidi, pygame)"
  pip install --quiet --upgrade pip
  pip install --quiet -r app/requirements.txt
  touch .venv/.deps-installed
fi

if [[ ! -d samples/wav ]] || [[ -z "$(ls -A samples/wav 2>/dev/null)" ]]; then
  echo "==> building samples/wav/ from samples/sources/ (first run)"
  bash tools/build_samples.sh
fi

mkdir -p app/presets

# On macOS, pygame may print to stderr but still works. Keep midi-hint lenient
# in case the TouchMe isn't plugged in here — the app is usable for editing
# presets even without MIDI.
exec python app/main.py \
  --samples samples/wav \
  --config app/config.local.json \
  --presets app/presets \
  --host 127.0.0.1 \
  --port 8080
