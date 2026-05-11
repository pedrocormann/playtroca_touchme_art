#!/usr/bin/env bash
# Build the playback library from samples/sources/<concept>/*.{mp3,wav,...}.
#
# Each *source file* becomes its own group (a directory of 30s chunks). The
# concept subfolders in samples/sources/ are just organizational for the artist —
# they're flattened in samples/wav/ so each source file shows up as one group
# the sampler can pick from. This gives the algorithm more granularity than
# lumping multiple sources into a single broad bucket.
#
# After building, we estimate each group's "darkness" (how much energy sits
# below 300 Hz vs above 3000 Hz) and write samples/wav/_order.txt with groups
# sorted dark→bright. The sampler reads this and the auto-assigner maps the
# darkest group to the lowest MIDI pad (C4) and the brightest to the highest (B4).
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$HERE/samples/sources"
DST="$HERE/samples/wav"
CHUNK_SECONDS="${CHUNK_SECONDS:-30}"
SILENCE_THRESH="${SILENCE_THRESH:--45dB}"
ANALYSIS_SECONDS="${ANALYSIS_SECONDS:-15}"

if ! command -v ffmpeg >/dev/null; then
  echo "ffmpeg not found. Install with: sudo apt install -y ffmpeg" >&2
  exit 1
fi

mkdir -p "$DST"

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9._-]+/_/g; s/_+/_/g; s/^_|_$//g'
}

FILTER="silenceremove=start_periods=1:start_duration=0.3:start_threshold=${SILENCE_THRESH},areverse,silenceremove=start_periods=1:start_duration=0.3:start_threshold=${SILENCE_THRESH},areverse,afade=t=in:d=0.05"

# ── 1) Chunk each source file into its own group directory ─────────────────
shopt -s nullglob nocaseglob
declare -a GROUP_DIRS=()
for group_dir in "$SRC"/*/; do
  for src in "$group_dir"*.{mp3,wav,flac,ogg,m4a,aac,opus}; do
    base="$(basename "$src")"
    stem="${base%.*}"
    stem_slug=$(slugify "$stem")
    out_dir="$DST/$stem_slug"
    GROUP_DIRS+=("$out_dir")
    mkdir -p "$out_dir"
    first_chunk="$out_dir/${stem_slug}_000.wav"
    if [[ -f "$first_chunk" && "$first_chunk" -nt "$src" ]]; then
      continue
    fi
    rm -f "$out_dir/${stem_slug}_"*.wav
    echo "→ $base → $stem_slug/"
    ffmpeg -loglevel error -y -i "$src" \
      -af "$FILTER" \
      -ar 44100 -ac 2 -sample_fmt s16 \
      -f segment -segment_time "$CHUNK_SECONDS" -reset_timestamps 1 \
      "$out_dir/${stem_slug}_%03d.wav"
  done
done
shopt -u nullglob nocaseglob

# Also pick up groups already on disk that don't have a source anymore
for d in "$DST"/*/; do
  d="${d%/}"
  case " ${GROUP_DIRS[*]} " in
    *" $d "*) ;;
    *) GROUP_DIRS+=("$d") ;;
  esac
done

# ── 2) Estimate brightness of each group ───────────────────────────────────
#
# mean_volume of low-pass (≤300Hz) vs high-pass (≥3000Hz) bands. The dB value
# returned by `volumedetect` is negative; larger (closer to 0) = louder in that
# band. Brightness = high_dB − low_dB (higher score → brighter).

mean_vol() {
  local file="$1" filt="$2"
  local out
  # volumedetect logs at "info" level — keep info but hide banner/progress
  out=$(ffmpeg -hide_banner -nostats -i "$file" -t "$ANALYSIS_SECONDS" \
        -af "${filt},volumedetect" -f null - 2>&1 || true)
  echo "$out" | awk -F: '/mean_volume/{gsub(/[ dB]/, "", $NF); print $NF; exit}'
}

ORDER_FILE="$DST/_order.txt"
TMP_SCORES="$(mktemp)"
echo "Analyzing brightness (low ≤300Hz vs high ≥3000Hz, ${ANALYSIS_SECONDS}s sample)…"
for gdir in "${GROUP_DIRS[@]}"; do
  [[ -d "$gdir" ]] || continue
  sample=$(ls "$gdir"/*.wav 2>/dev/null | head -1 || true)
  [[ -z "$sample" ]] && continue
  group=$(basename "$gdir")
  low=$(mean_vol "$sample" "lowpass=f=300")
  high=$(mean_vol "$sample" "highpass=f=3000")
  # default to 0 if parsing failed
  low="${low:-0}"
  high="${high:-0}"
  score=$(awk -v h="$high" -v l="$low" 'BEGIN{printf "%.2f", h - l}')
  printf "  %-30s low=%s dB  high=%s dB  brightness=%s\n" "$group" "$low" "$high" "$score"
  printf "%s\t%s\n" "$score" "$group" >> "$TMP_SCORES"
done

# Sort numeric ascending (dark first, bright last) and emit group names
sort -n "$TMP_SCORES" | awk -F'\t' '{print $2}' > "$ORDER_FILE"
rm -f "$TMP_SCORES"

echo
echo "Group order (dark → bright) written to $ORDER_FILE:"
nl -ba "$ORDER_FILE"

# Summary
echo
total=0
echo "Chunks per group:"
for g in $(cat "$ORDER_FILE"); do
  n=$(ls "$DST/$g"/*.wav 2>/dev/null | wc -l | tr -d ' ')
  printf "  %-30s %4s chunks\n" "$g" "$n"
  total=$((total + n))
done
echo "Total: $total chunks across $(wc -l < "$ORDER_FILE" | tr -d ' ') groups."
