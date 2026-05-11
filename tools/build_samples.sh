#!/usr/bin/env bash
# Convert every audio in samples/sources/ → 16-bit stereo 44.1kHz WAV in samples/wav/.
# Idempotent: skips files where the WAV already exists and is newer than the source.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$HERE/samples/sources"
DST="$HERE/samples/wav"

mkdir -p "$DST"

if ! command -v ffmpeg >/dev/null; then
  echo "ffmpeg not found. Install with: sudo apt install -y ffmpeg" >&2
  exit 1
fi

shopt -s nullglob nocaseglob
count=0
for src in "$SRC"/*.{mp3,wav,flac,ogg,m4a,aac}; do
  base="$(basename "$src")"
  stem="${base%.*}"
  # Slugify: lowercase, replace spaces and weird chars with _
  slug=$(echo "$stem" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/_/g; s/_+/_/g; s/^_|_$//g')
  out="$DST/${slug}.wav"
  if [[ -f "$out" && "$out" -nt "$src" ]]; then
    continue
  fi
  echo "→ $base → ${slug}.wav"
  ffmpeg -loglevel error -y -i "$src" -ar 44100 -ac 2 -sample_fmt s16 "$out"
  count=$((count+1))
done
shopt -u nullglob nocaseglob

echo "Built $count file(s). Total in $DST:"
ls -1 "$DST" | sed 's/^/  /'
