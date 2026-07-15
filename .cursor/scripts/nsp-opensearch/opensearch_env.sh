#!/usr/bin/env bash
# Source OpenSearch / NSP gateway env for nsp_opensearch_log_report.py
#
# Usage:
#   cd agentic-workspace/.cursor/scripts && source opensearch_env.sh
#
# First time:
#   cp opensearch_env.local.example opensearch_env.local
#   # edit opensearch_env.local

# Resolve script directory when sourced as `source opensearch_env.sh` (dirname would otherwise be empty).
_SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$_SCRIPT_PATH" != /* ]]; then
  _SCRIPT_PATH="$(pwd)/${_SCRIPT_PATH#./}"
fi
SCRIPT_DIR="$(cd "$(dirname "$_SCRIPT_PATH")" && pwd)"
LOCAL_FILE="${SCRIPT_DIR}/opensearch_env.local"
unset _SCRIPT_PATH

if [[ -f "$LOCAL_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$LOCAL_FILE"
fi

# NSP_IP as fallback for NSP_GATEWAY
if [[ -z "$NSP_GATEWAY" && -n "$NSP_IP" ]]; then
  NSP_GATEWAY="$NSP_IP"
fi

if [[ -z "$NSP_GATEWAY" || -z "$NSP_USER" || -z "$NSP_PASSWORD" ]]; then
  echo "OpenSearch env incomplete. Set NSP_GATEWAY (or NSP_IP), NSP_USER, NSP_PASSWORD in $LOCAL_FILE" >&2
  echo "  cp opensearch_env.local.example opensearch_env.local" >&2
  return 1 2>/dev/null || exit 1
fi

export NSP_GATEWAY NSP_USER NSP_PASSWORD
export NSP_OPENSEARCH_PORT="${NSP_OPENSEARCH_PORT:-9200}"
export NSP_HTTPS_SCHEME="${NSP_HTTPS_SCHEME:-https}"
export NSP_VERIFY_TLS="${NSP_VERIFY_TLS:-1}"

echo "OpenSearch env loaded (NSP_GATEWAY=$NSP_GATEWAY, port=$NSP_OPENSEARCH_PORT, verify_tls=$NSP_VERIFY_TLS)"
