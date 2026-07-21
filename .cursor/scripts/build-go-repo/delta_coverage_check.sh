#!/usr/bin/env bash
# CI-parity delta coverage check for .go-make Go repos.
#
# Matches Jenkins exactly:
#   1. history.diff from the latest [jenkins] commit
#   2. BUILDER=docker make test  (gotestsum -coverpkg=./... ./... in build image)
#   3. gocover-cobertura inside the build image (relative paths: internal/...)
#   4. build-unittest-coverage-delta:1 container
#
# Usage (from repo root or pass REPO_DIR):
#   bash workspace-settings/.cursor/scripts/build-go-repo/delta_coverage_check.sh
#   bash workspace-settings/.cursor/scripts/build-go-repo/delta_coverage_check.sh /path/to/repo
#
# Options:
#   --skip-test     Reuse existing build/test-results/test/cobertura/coverage.xml
#   --threshold N   Expected minimum % (default 75; buffer above Jenkins 70%)

set -euo pipefail

SKIP_TEST=false
THRESHOLD=75
REPO_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-test) SKIP_TEST=true; shift ;;
    --threshold) THRESHOLD="${2:?}"; shift 2 ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
    *)
      if [[ -z "$REPO_DIR" ]]; then
        REPO_DIR="$1"
      else
        echo "Unknown argument: $1" >&2
        exit 2
      fi
      shift
      ;;
  esac
done

REPO_DIR="${REPO_DIR:-$(pwd)}"
REPO_DIR="$(cd "$REPO_DIR" && pwd)"

if [[ ! -f "$REPO_DIR/.go-make/go.mk" ]]; then
  echo "error: $REPO_DIR is not a .go-make Go repo (missing .go-make/go.mk)" >&2
  exit 2
fi

export BUILDER=docker
DELTA_IMAGE="orbw-artifactory.ca.alcatel-lucent.com:8081/nokia-nsp-docker-local/build-unittest-coverage-delta:1"
COBERTURA_XML="$REPO_DIR/build/test-results/test/cobertura/coverage.xml"
HISTORY_DIFF="$REPO_DIR/history.diff"

cd "$REPO_DIR"

BASE="$(git log --grep='\[jenkins\]' --pretty=format:'%h' -1)"
if [[ -z "$BASE" ]]; then
  echo "error: no [jenkins] baseline commit found; cannot build history.diff" >&2
  exit 2
fi

echo "==> Jenkins baseline: $BASE"
git diff "$BASE" > "$HISTORY_DIFF"
echo "==> history.diff: $(wc -l < "$HISTORY_DIFF") lines ($(git diff "$BASE" --stat | tail -1))"

if [[ "$SKIP_TEST" != true ]]; then
  echo "==> Running BUILDER=docker make test (CI-equivalent coverage)..."
  if ! make test; then
    echo "error: make test failed; fix tests before delta-coverage can pass in Jenkins" >&2
    exit 1
  fi
fi

if [[ ! -f "$COBERTURA_XML" ]]; then
  echo "error: missing $COBERTURA_XML — run make test first" >&2
  exit 2
fi

# Host gocover-cobertura prefixes filenames with the Go module path. The delta
# container matches history.diff paths (internal/...) and silently passes (~100%)
# when cobertura uses module-qualified paths. Jenkins runs gocover-cobertura in
# the build image, which emits relative paths.
if grep -q 'filename="[^"]*/' "$COBERTURA_XML" && \
   grep -qE 'filename="[a-zA-Z0-9._-]+\.[a-zA-Z0-9._-]+/' "$COBERTURA_XML"; then
  # Heuristic: module path contains a dot before the first slash (e.g. nsp.nokia.com/...)
  if grep -qE 'filename="[^/]+\.[^/]+/' "$COBERTURA_XML"; then
    echo "error: cobertura filenames look module-qualified (host gocover-cobertura)." >&2
    echo "       Re-run BUILDER=docker make test so cobertura is produced in the build image." >&2
    echo "       Host-generated cobertura causes a false 100% delta pass." >&2
    exit 2
  fi
fi

echo "==> Running delta-coverage (docker)..."
set +e
DELTA_OUT="$(docker run --rm -v "$REPO_DIR":/app/data/ "$DELTA_IMAGE" \
  data/history.diff data/build/test-results/test/cobertura/coverage.xml 2>&1)"
DELTA_RC=$?
set -e

echo "$DELTA_OUT"

if echo "$DELTA_OUT" | grep -q 'Threshold of .* not passed'; then
  PCT="$(echo "$DELTA_OUT" | grep -oE '[0-9.]+% of changes covered' | tail -1 || true)"
  echo "" >&2
  echo "FAIL: delta coverage below Jenkins threshold ($THRESHOLD%). ${PCT:-see output above}" >&2
  echo "Uncovered files (ratio < 1.0):" >&2
  echo "$DELTA_OUT" | grep -E ', 0(\.0+)?$|, 0\.[0-9]' | head -30 >&2 || true
  exit 1
fi

PCT_NUM="$(echo "$DELTA_OUT" | grep -oE '[0-9.]+% of changes covered' | tail -1 | sed 's/%.*//' || true)"
if [[ -n "$PCT_NUM" ]] && awk -v p="$PCT_NUM" -v t="$THRESHOLD" 'BEGIN{exit !(p+0 >= t+0)}'; then
  echo "PASS: delta coverage OK (${PCT_NUM}%, threshold ${THRESHOLD}%)"
  exit 0
fi

if echo "$DELTA_OUT" | grep -q '100% of changes covered'; then
  echo "PASS: delta coverage OK (100%, threshold ${THRESHOLD}%)"
  exit 0
fi

echo "error: unexpected delta-coverage output (exit $DELTA_RC)" >&2
exit "${DELTA_RC:-1}"
