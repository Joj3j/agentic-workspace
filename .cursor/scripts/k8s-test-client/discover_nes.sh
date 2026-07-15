#!/usr/bin/env bash
# discover_nes.sh — list NEs registered in device-registry, with optional filters.
#
# Wraps k8s_run_test_client.sh --client device-registry -- -cmd get-ne-entries
# so the agent (or a smoke test) can fetch a clean list of NE IDs from the K8s
# cluster without driving the interactive menu.
#
# Filters and output format mirror the device-registry GetNeEntries RPC:
#   --ne-type     <str>   filter by NE type     (e.g. SR-7750, 7220-IXR-SRL)
#   --ne-version  <str>   filter by NE version  (e.g. 22.10.R1)
#   --protocol    <str>   filter by protocol    (netconf | gnmi)
#   --format      <fmt>   output format         (ids | tsv | json | text, default: ids)
#   --limit       <n>     truncate to first n entries (after filter)
#
# Output:
#   format=ids   : one neId per line on stdout (default; ideal for shell pipelines)
#   format=tsv   : ne_id\tne_type\tne_version\tne_vendor  (with header)
#   format=json  : compact JSON array
#   format=text  : human-readable banner + per-NE block
#
# Example:
#   source .cursor/scripts/k8s-test-client/k8s_test_env.sh
#   bash .cursor/scripts/k8s-test-client/discover_nes.sh --ne-type SR-7750 --protocol netconf
#   bash .cursor/scripts/k8s-test-client/discover_nes.sh --protocol gnmi --format tsv
#
# Exit codes:
#   0  success (zero or more entries printed)
#   1  RPC failure or invalid flags
#
# Note: ALL logs from k8s_run_test_client.sh (port-forward setup, build messages)
# are sent to stderr by this wrapper so stdout stays parseable.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

NE_TYPE=""
NE_VERSION=""
PROTOCOL=""
FORMAT="ids"
LIMIT=""

usage() {
  cat >&2 <<EOF
Usage: $0 [--ne-type <t>] [--ne-version <v>] [--protocol <p>] [--format ids|tsv|json|text] [--limit <n>]

Sources of truth:
  Filters and format flags match device-registry GetNeEntries.
  Connection uses the same K8s tunnel as k8s_run_test_client.sh --client device-registry.

Examples:
  $0 --ne-type SR-7750 --protocol netconf
  $0 --ne-type 7220-IXR-SRL --format tsv
  $0 --format json --limit 4
EOF
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ne-type)    NE_TYPE="$2"; shift 2 ;;
    --ne-version) NE_VERSION="$2"; shift 2 ;;
    --protocol)   PROTOCOL="$2"; shift 2 ;;
    --format)     FORMAT="$2"; shift 2 ;;
    --limit)      LIMIT="$2"; shift 2 ;;
    -h|--help)    usage ;;
    *)            echo "Unknown arg: $1" >&2; usage ;;
  esac
done

case "$FORMAT" in
  ids|tsv|json|text) ;;
  *) echo "Error: --format must be one of ids|tsv|json|text (got: $FORMAT)" >&2; exit 1 ;;
esac

# Build the test-client argv. Skip empty filters so the proto-optional fields
# are left unset (the server treats them as "no filter").
client_args=(-cmd get-ne-entries -format "$FORMAT")
if [[ -n "$NE_TYPE" ]]; then
  client_args+=(-ne-type "$NE_TYPE")
fi
if [[ -n "$NE_VERSION" ]]; then
  client_args+=(-ne-version "$NE_VERSION")
fi
if [[ -n "$PROTOCOL" ]]; then
  client_args+=(-protocol "$PROTOCOL")
fi

# Run k8s_run_test_client.sh. Its setup chatter (port-forward, build, connect
# banner) goes to fd 3 -> stderr; the test-client's stdout is captured.
# We use a temp file because bash process substitution would let stderr/stdout
# interleave even with `2>` redirection on the surrounding bash.
tmp_out="$(mktemp)"
trap 'rm -f "$tmp_out"' EXIT

if ! bash "${SCRIPT_DIR}/k8s_run_test_client.sh" --client device-registry -- "${client_args[@]}" \
      > "$tmp_out" 2> >(awk '{print "[discover_nes] " $0}' >&2); then
  echo "Error: device-registry query failed" >&2
  exit 1
fi

# k8s_run_test_client.sh prepends a few setup lines on stdout ("Building ...",
# "Starting port-forward ...", "Port-forward ready ...", "Connecting to ...")
# and appends teardown chatter after the test-client exits ("Cleaning up
# remote port-forward ...", fuser pid). kubectl port-forward also logs
# "Handling connection for <port>" via SSH to our stdout.
# Strip everything that isn't test-client output:
#   - Drop everything up to and including the "Connecting to <client>" banner.
#   - Drop kubectl "Handling connection for ..." lines (can appear anywhere
#     after the test-client dials).
#   - Drop teardown lines that follow the test-client exiting.
awk '
  BEGIN { in_payload = 0 }
  /^Connecting to device-registry at / { in_payload = 1; next }
  !in_payload                          { next }
  /^Handling connection for /          { next }
  /^Cleaning up remote port-forward/   { next }
  /^[[:space:]]+[0-9]+$/               { next }   # bare fuser pid output
  { print }
' "$tmp_out" | {
  if [[ -n "$LIMIT" ]]; then
    case "$FORMAT" in
      ids)  head -n "$LIMIT" ;;
      tsv)  awk -v n="$LIMIT" 'NR==1 || NR<=n+1' ;;
      json) cat ;;  # JSON is a single line, --limit not honored
      text) head -n $((LIMIT + 1)) ;;  # 1 banner line + N entries
    esac
  else
    cat
  fi
}
