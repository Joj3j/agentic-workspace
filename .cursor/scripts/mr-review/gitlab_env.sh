#!/usr/bin/env bash
# Source this file before running post_review.py when using the local token file.
# GITLAB_HOST is auto-detected from the git remote; only GITLAB_TOKEN is required.
#
#   source .cursor/scripts/mr-review/gitlab_env.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_ENV="$SCRIPT_DIR/gitlab_env.local"

if [[ -f "$LOCAL_ENV" ]]; then
    # shellcheck source=/dev/null
    source "$LOCAL_ENV"
else
    echo "ERROR: $LOCAL_ENV not found." >&2
    echo "Copy gitlab_env.local.example → gitlab_env.local and set GITLAB_TOKEN." >&2
    return 1 2>/dev/null || exit 1
fi

: "${GITLAB_TOKEN:?GITLAB_TOKEN must be set in gitlab_env.local}"
export GITLAB_TOKEN

# Export GITLAB_HOST only if explicitly set in the local file
[[ -n "$GITLAB_HOST" ]] && export GITLAB_HOST
