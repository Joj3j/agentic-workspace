#!/usr/bin/env bash
# Source this script to set Confluence env vars for confluence_read_page.py and confluence_create_page.py.
#
# Usage (invoke first, then run Confluence scripts in the same shell):
#   source .cursor/scripts/confluence_env.sh
#   # or from repo root:
#   source agentic-workspace/.cursor/scripts/confluence_env.sh
#
# First time: copy confluence_env.local.example to confluence_env.local and set your values.
# confluence_env.local is gitignored.

# Resolve directory containing this script. A plain ${BASH_SOURCE[0]%/*} breaks when the script is
# sourced as `source confluence_env.sh` (no slash in BASH_SOURCE[0]) — LOCAL_FILE would never match.
_script="${BASH_SOURCE[0]:-$0}"
SCRIPT_DIR="$(cd -P "$(dirname "$_script")" && pwd)"
LOCAL_FILE="${SCRIPT_DIR}/confluence_env.local"

if [[ -f "$LOCAL_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$LOCAL_FILE"
  # Support CONFLUENCE_CURSOR_TOKEN (Confluence token name) or CONFLUENCE_PASSWORD as alias for CONFLUENCE_API_TOKEN
  if [[ -z "$CONFLUENCE_API_TOKEN" ]]; then
    if [[ -n "$CONFLUENCE_CURSOR_TOKEN" ]]; then
      CONFLUENCE_API_TOKEN="$CONFLUENCE_CURSOR_TOKEN"
    elif [[ -n "$CONFLUENCE_PASSWORD" ]]; then
      CONFLUENCE_API_TOKEN="$CONFLUENCE_PASSWORD"
    fi
  fi
  if [[ -n "$CONFLUENCE_BASE_URL" && -n "$CONFLUENCE_USERNAME" && -n "$CONFLUENCE_API_TOKEN" ]]; then
    export CONFLUENCE_BASE_URL CONFLUENCE_USERNAME CONFLUENCE_API_TOKEN
    echo "Confluence env loaded (CONFLUENCE_BASE_URL=$CONFLUENCE_BASE_URL)"
  else
    echo "confluence_env: $LOCAL_FILE exists but one or more of CONFLUENCE_BASE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN (or CONFLUENCE_CURSOR_TOKEN or CONFLUENCE_PASSWORD) are unset" >&2
    return 1 2>/dev/null || exit 1
  fi
else
  echo "Confluence env not set. Create $LOCAL_FILE from confluence_env.local.example and set your values, then source this script again." >&2
  echo "  cp confluence_env.local.example confluence_env.local" >&2
  return 1 2>/dev/null || exit 1
fi
