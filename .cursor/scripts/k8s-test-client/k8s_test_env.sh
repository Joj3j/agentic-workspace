#!/usr/bin/env bash
# Source K8s test-client env for k8s_run_test_client.sh
#
# Usage:
#   cd workspace-settings/.cursor/scripts && source k8s_test_env.sh
#
# First time:
#   cp k8s_test_env.local.example k8s_test_env.local
#   # edit k8s_test_env.local with your jump host IP and SSH credentials

_SCRIPT_PATH="${BASH_SOURCE[0]}"
if [[ "$_SCRIPT_PATH" != /* ]]; then
  _SCRIPT_PATH="$(pwd)/${_SCRIPT_PATH#./}"
fi
SCRIPT_DIR="$(cd "$(dirname "$_SCRIPT_PATH")" && pwd)"
LOCAL_FILE="${SCRIPT_DIR}/k8s_test_env.local"
unset _SCRIPT_PATH

if [[ -f "$LOCAL_FILE" ]]; then
  # shellcheck source=/dev/null
  source "$LOCAL_FILE"
fi

if [[ -z "$K8S_NODE_IP" ]]; then
  echo "K8s env incomplete. Set K8S_NODE_IP in $LOCAL_FILE" >&2
  echo "  cp k8s_test_env.local.example k8s_test_env.local" >&2
  return 1 2>/dev/null || exit 1
fi

export K8S_NODE_IP
export K8S_SSH_USER="${K8S_SSH_USER:-root}"
export K8S_SSH_KEY="${K8S_SSH_KEY:-}"
export K8S_SSH_OPTS="${K8S_SSH_OPTS:-}"
export CLS_FWD_PORT="${CLS_FWD_PORT:-40055}"
export DR_FWD_PORT="${DR_FWD_PORT:-40058}"
export GNMI_FWD_PORT="${GNMI_FWD_PORT:-40051}"

# Ensure jump host bypasses any HTTP proxy (gRPC honours HTTP_PROXY)
if [[ -n "${HTTP_PROXY:-}${HTTPS_PROXY:-}${http_proxy:-}${https_proxy:-}" ]]; then
  case ",${NO_PROXY:-}," in
    *",${K8S_NODE_IP},"*) ;;
    *) export NO_PROXY="${NO_PROXY:+${NO_PROXY},}${K8S_NODE_IP}"
       export no_proxy="${no_proxy:+${no_proxy},}${K8S_NODE_IP}" ;;
  esac
fi

echo "K8s test env loaded (jump=$K8S_NODE_IP, ssh_user=$K8S_SSH_USER, cls=:$CLS_FWD_PORT, dr=:$DR_FWD_PORT, gnmi=:$GNMI_FWD_PORT)"
