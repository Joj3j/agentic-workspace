#!/usr/bin/env bash
# pprof_snapshot.sh — download common profiles and print go tool pprof -top summaries.
set -euo pipefail

PPROF_URL="${PPROF_URL:-http://127.0.0.1:8080}"
OUT="${OUT:-./pprof-snapshots/$(date +%Y%m%d-%H%M%S)}"
SECONDS="${PROFILE_SECONDS:-30}"

mkdir -p "$OUT"

fetch() {
  local name=$1
  local url=$2
  local out="$OUT/${name}.prof"
  echo "Fetching $url -> $out"
  curl -sfSL "$url" -o "$out"
  if command -v go >/dev/null 2>&1; then
    echo "--- top: $name ---"
  go tool pprof -top "$out" 2>/dev/null | head -25 || true
  fi
}

fetch cpu "${PPROF_URL}/debug/pprof/profile?seconds=${SECONDS}"
fetch heap "${PPROF_URL}/debug/pprof/heap"
fetch allocs "${PPROF_URL}/debug/pprof/allocs"
fetch goroutine "${PPROF_URL}/debug/pprof/goroutine"
fetch mutex "${PPROF_URL}/debug/pprof/mutex"
fetch block "${PPROF_URL}/debug/pprof/block"

echo "Snapshots in $OUT"
