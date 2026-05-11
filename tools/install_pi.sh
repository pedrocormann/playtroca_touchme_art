#!/usr/bin/env bash
# Run ON THE PI (or from a deploy script via ssh).
# - Creates /opt/playtronica venv with --system-site-packages (reuses apt pygame/rtmidi/flask)
# - Installs mido via pip
# - Builds samples (mp3 → wav)
# - Installs and enables the systemd service
set -euo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-/opt/playtronica}"
USER_NAME="${PLAYTRONICA_USER:-piripak}"

echo "==> Installing into $PROJECT_ROOT (user: $USER_NAME)"

sudo mkdir -p "$PROJECT_ROOT"
sudo chown -R "$USER_NAME:$USER_NAME" "$PROJECT_ROOT"

# Make sure system deps are present (idempotent)
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3-pygame python3-rtmidi python3-flask python3-venv python3-pip \
  ffmpeg alsa-utils

# Create venv that inherits apt-installed C-extensions
if [[ ! -d "$PROJECT_ROOT/venv" ]]; then
  python3 -m venv --system-site-packages "$PROJECT_ROOT/venv"
fi
"$PROJECT_ROOT/venv/bin/pip" install --quiet --upgrade pip
"$PROJECT_ROOT/venv/bin/pip" install --quiet mido

# Build samples
if [[ -d "$PROJECT_ROOT/samples/sources" ]]; then
  bash "$PROJECT_ROOT/tools/build_samples.sh"
fi

# Make sure piripak is in the audio group (for ALSA access in the service)
sudo usermod -a -G audio "$USER_NAME" || true

# Install systemd units (sampler + audio-max)
sudo cp "$PROJECT_ROOT/systemd/playtronica.service" /etc/systemd/system/playtronica.service
sudo cp "$PROJECT_ROOT/systemd/audio-max.service"    /etc/systemd/system/audio-max.service
sudo systemctl daemon-reload
sudo systemctl enable playtronica.service audio-max.service

# Default audio output: jack 3.5mm
sudo amixer -c Headphones cset numid=3 1 >/dev/null 2>&1 || true
# Apply now too (don't wait for next boot)
sudo systemctl start audio-max.service || true

# Drop any flat-layout WAVs left over from the v1 (pre-group) build
find "$PROJECT_ROOT/samples/wav" -maxdepth 1 -type f -name "*.wav" -delete 2>/dev/null || true

# Kiosk autostart: Chromium fullscreen → http://localhost:8080
sudo install -m 0755 "$PROJECT_ROOT/tools/playtronica-kiosk.sh" /usr/local/bin/playtronica-kiosk.sh
mkdir -p "$HOME/.config/autostart"
install -m 0644 "$PROJECT_ROOT/systemd/playtronica-kiosk.desktop" "$HOME/.config/autostart/playtronica-kiosk.desktop"
# Disable screen blanking via raspi-config when available
sudo raspi-config nonint do_blanking 1 2>/dev/null || true

echo "==> Install OK"
echo "    Service:  sudo systemctl restart playtronica"
echo "    Logs:     journalctl -u playtronica -f"
echo "    Web UI:   http://$(hostname -I | awk '{print $1}'):8080"
echo "    Kiosk:    Chromium will auto-launch fullscreen on next desktop login"
