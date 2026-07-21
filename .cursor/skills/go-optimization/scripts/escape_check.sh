#!/usr/bin/env bash
# escape_check.sh — rank escape-to-heap compiler messages per file:line.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 ./internal/pkg/..." >&2
  exit 1
fi

tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

go build -gcflags='-m -l' "$@" 2>&1 | tee "$tmp" >/dev/null || true

if ! grep -qE 'escapes to heap|moved to heap' "$tmp"; then
  echo "No escape messages (or build failed — inspect $tmp)."
  exit 0
fi

grep -E 'escapes to heap|moved to heap' "$tmp" | sed -E 's/^# //' | awk '
{
  line = $0
  if (match(line, /:[0-9]+:/)) {
    pos = RSTART
    rest = substr(line, pos)
    split(rest, a, ":")
    key = a[1] ":" a[2]
    count[key]++
    if (!(key in sample)) sample[key] = line
  }
}
END {
  for (k in count) print count[k], k, sample[k]
}' | sort -rn | head -40
