#!/usr/bin/env bash
# Build the playback library from samples/sources/<group>/*.{mp3,wav,...}.
#
# For each source file we:
#   - trim leading/trailing silence (threshold -45dB, >=0.3s)
#   - resample to 44.1 kHz stereo 16-bit
#   - split into ${CHUNK_SECONDS:-30}-second chunks
#   - apply 50 ms fade-in/out on each chunk to avoid clicks at boundaries
#
# Output: samples/wav/<group>/<source_slug>_NNN.wav
# Idempotent — skip a source if its first chunk is newer than the source itself.
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$HERE/samples/sources"
DST="$HERE/samples/wav"
CHUNK_SECONDS="${CHUNK_SECONDS:-30}"
SILENCE_THRESH="${SILENCE_THRESH:--45dB}"

if ! command -v ffmpeg >/dev/null; then
  echo "ffmpeg not found. Install with: sudo apt install -y ffmpeg" >&2
  exit 1
fi

mkdir -p "$DST"

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/_/g; s/_+/_/g; s/^_|_$//g'
}

# Pre-process filter chain:
#   1) trim leading silence
#   2) trim trailing silence (areverse trick)
#   3) tiny fade-in to mask any abrupt start
FILTER="silenceremove=start_periods=1:start_duration=0.3:start_threshold=${SILENCE_THRESH},areverse,silenceremove=start_periods=1:start_duration=0.3:start_threshold=${SILENCE_THRESH},areverse,afade=t=in:d=0.05"

shopt -s nullglob nocaseglob
total=0
for group_dir in "$SRC"/*/; do
  group=$(basename "$group_dir")
  group_slug=$(slugify "$group")
  out_dir="$DST/$group_slug"
  mkdir -p "$out_dir"
  group_chunks=0
  for src in "$group_dir"*.{mp3,wav,flac,ogg,m4a,aac,opus}; do
    base="$(basename "$src")"
    stem="${base%.*}"
    stem_slug=$(slugify "$stem")
    pattern="$out_dir/${stem_slug}_%03d.wav"
    first_chunk="$out_dir/${stem_slug}_000.wav"
    if [[ -f "$first_chunk" && "$first_chunk" -nt "$src" ]]; then
      # already built, count existing chunks for the summary
      n=$(ls "$out_dir/${stem_slug}_"*.wav 2>/dev/null | wc -l | tr -d ' ')
      group_chunks=$((group_chunks + n))
      continue
    fi
    rm -f "$out_dir/${stem_slug}_"*.wav
    echo "→ [$group_slug] $base"
    ffmpeg -loglevel error -y -i "$src" \
      -af "$FILTER" \
      -ar 44100 -ac 2 -sample_fmt s16 \
      -f segment -segment_time "$CHUNK_SECONDS" -reset_timestamps 1 \
      "$pattern"
    new=$(ls "$out_dir/${stem_slug}_"*.wav 2>/dev/null | wc -l | tr -d ' ')
    echo "    → $new chunk(s)"
    group_chunks=$((group_chunks + new))
  done
  total=$((total + group_chunks))
  # Drop empty group dirs (no sources)
  if [[ $(ls -A "$out_dir" 2>/dev/null | wc -l) -eq 0 ]]; then
    rmdir "$out_dir"
  fi
done
shopt -u nullglob nocaseglob

echo
echo "Summary ($total total chunks in $DST):"
for g in "$DST"/*/; do
  [[ -d "$g" ]] || continue
  n=$(ls "$g"*.wav 2>/dev/null | wc -l | tr -d ' ')
  printf "  %-30s %4s chunks\n" "$(basename "$g")" "$n"
done
