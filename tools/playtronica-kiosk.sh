#!/usr/bin/env bash
# Launch Chromium in kiosk mode pointing at the local Flask UI.
# Waits for the service to be reachable to avoid flashing an error page.
set -u

URL="${PLAYTRONICA_URL:-http://localhost:8080}"

# Disable screen blanking / DPMS where available
xset s noblank 2>/dev/null || true
xset s off 2>/dev/null || true
xset -dpms 2>/dev/null || true

# Wait up to 60s for the service to be reachable
for _ in $(seq 1 60); do
  if curl -sf -o /dev/null --max-time 1 "$URL/api/status"; then break; fi
  sleep 1
done

# Pick the chromium binary that exists
BIN=""
for cand in chromium-browser chromium google-chrome; do
  if command -v "$cand" >/dev/null 2>&1; then BIN="$cand"; break; fi
done
if [[ -z "$BIN" ]]; then
  echo "No chromium binary found." >&2
  exit 1
fi

exec "$BIN" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-features=TranslateUI \
  --disable-session-crashed-bubble \
  --check-for-update-interval=31536000 \
  --no-first-run \
  --start-fullscreen \
  --overscroll-history-navigation=0 \
  --app="$URL"
