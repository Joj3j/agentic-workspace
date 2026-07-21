#!/usr/bin/env bash
# bench_delta.sh — benchstat compare current HEAD vs BASE_REF for one package/benchmark.
set -euo pipefail

PKG="./..."
BENCH="."
COUNT=10
BASE_REF="HEAD~1"

usage() {
  echo "Usage: $0 [-pkg PATH] [-bench REGEX] [-count N] [-base REF]" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -pkg) PKG="$2"; shift 2 ;;
    -bench) BENCH="$2"; shift 2 ;;
    -count) COUNT="$2"; shift 2 ;;
    -base) BASE_REF="$2"; shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown arg: $1" >&2; usage ;;
  esac
done

if ! command -v benchstat >/dev/null 2>&1; then
  echo "benchstat not found; install: go install golang.org/x/perf/cmd/benchstat@latest" >&2
  exit 1
fi

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT

run_bench() {
  local label=$1
  go test -bench="$BENCH" -benchmem -count="$COUNT" -run=^$ "$PKG" >"$dir/${label}.txt" 2>&1
}

current_branch=$(git rev-parse --abbrev-ref HEAD)
current_sha=$(git rev-parse HEAD)

git stash push -u -m "bench_delta autostash" >/dev/null 2>&1 || true
stashed=$?

git checkout "$BASE_REF" >/dev/null 2>&1
run_bench base
git checkout "$current_sha" >/dev/null 2>&1
if [[ $stashed -eq 0 ]]; then
  git stash pop >/dev/null 2>&1 || true
fi

run_bench head

echo "=== benchstat base ($BASE_REF) vs head ($current_sha) ==="
benchstat "$dir/base.txt" "$dir/head.txt"
