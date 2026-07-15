#!/usr/bin/env bash
# Source RESTCONF / NSP gateway env for smoke_restconf.py
#
# Usage:
#   cd agentic-workspace/.cursor/scripts/smoke-run-deployer
#   source restconf_env.sh
#
# First time:
#   cp restconf_env.local.example restconf_env.local
#   # edit restconf_env.local

_SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$_SCRIPT_PATH" != /* ]]; then
  _SCRIPT_PATH="$(pwd)/${_SCRIPT_PATH#./}"
fi
SCRIPT_DIR="$(cd "$(dirname "$_SCRIPT_PATH")" && pwd)"
LOCAL_FILE="${SCRIPT_DIR}/restconf_env.local"
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
  echo "RESTCONF env incomplete. Set NSP_GATEWAY (or NSP_IP), NSP_USER, NSP_PASSWORD in $LOCAL_FILE" >&2
  echo "  cp restconf_env.local.example restconf_env.local" >&2
  return 1 2>/dev/null || exit 1
fi

export NSP_GATEWAY NSP_USER NSP_PASSWORD
export RESTCONF_PORT="${RESTCONF_PORT:-8545}"
export NSP_HTTPS_SCHEME="${NSP_HTTPS_SCHEME:-https}"
export NSP_VERIFY_TLS="${NSP_VERIFY_TLS:-0}"

echo "RESTCONF env loaded (NSP_GATEWAY=$NSP_GATEWAY, port=$RESTCONF_PORT, verify_tls=$NSP_VERIFY_TLS)"
