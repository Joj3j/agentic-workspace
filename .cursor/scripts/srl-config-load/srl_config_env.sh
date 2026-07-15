#!/usr/bin/env bash
# Source SRL config-load env for srl_load_config.py
#
# Usage (same shell as the script):
#   cd agentic-workspace/.cursor/scripts && source srl_config_env.sh
#
# First time:
#   cp srl_config_env.local.example srl_config_env.local
#   # edit srl_config_env.local: SRL_USER, SRL_PASSWORD, versions

_SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$_SCRIPT_PATH" != /* ]]; then
  _SCRIPT_PATH="$(pwd)/${_SCRIPT_PATH#./}"
fi
SCRIPT_DIR="$(cd "$(dirname "$_SCRIPT_PATH")" && pwd)"
LOCAL_FILE="${SCRIPT_DIR}/srl_config_env.local"
unset _SCRIPT_PATH

if [[ -f "$LOCAL_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$LOCAL_FILE"
fi

export SRL_USER="${SRL_USER:-admin}"
export SRL_PASSWORD="${SRL_PASSWORD:-admin}"
export SRL_SOURCE_VER="${SRL_SOURCE_VER:-22.11}"
export SRL_TARGET_VER="${SRL_TARGET_VER:-25.10}"

echo "SRL env loaded (user=${SRL_USER}, source_ver=${SRL_SOURCE_VER}, target_ver=${SRL_TARGET_VER})"
