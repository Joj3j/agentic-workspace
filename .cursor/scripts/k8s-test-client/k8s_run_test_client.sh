#!/usr/bin/env bash
# Build and run a test client against K8s-deployed services.
#
# Runs kubectl port-forward on the jump host (--address 0.0.0.0) so the
# dev machine can reach the K8s service directly. The client connects to
# the jump host IP on the forwarded port.
#
# Usage:
#   source k8s_test_env.sh
#   bash k8s_run_test_client.sh --client comm-layer-server
#   bash k8s_run_test_client.sh --status --client comm-layer-server
#   bash k8s_run_test_client.sh --client device-registry [-- extra flags]

set -euo pipefail

WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"

usage() {
  cat <<EOF
Usage: $0 --client <name> [options] [-- extra-flags...]

Clients:
  comm-layer-server       rpc_test_client         (gRPC -> jump:${CLS_FWD_PORT:-40055})
  comm-layer-benchmark    benchmark_client        (gRPC -> jump:${CLS_FWD_PORT:-40055}, async bulk write smoke/load)
  device-registry         test_client             (gRPC -> jump:${DR_FWD_PORT:-40058})
  comm-worker-gnmi        worker_test_client      (gRPC -> jump:${GNMI_FWD_PORT:-40051})
  comm-subscription-server subscription_test_client (gRPC -> jump:${SUB_FWD_PORT:-40056})

Commands:
  --status            Check service and pod status on the cluster via SSH.

Options:
  --client <name>     Required. One of the client names above.
  --build             Force rebuild even if the binary exists.
  --                  Everything after this is forwarded to the test client.

Environment (source k8s_test_env.sh first):
  K8S_NODE_IP           Jump host IP      (required)
  K8S_SSH_USER          SSH user          (default: root)
  K8S_SSH_KEY           SSH key path      (optional)
  K8S_SSH_OPTS          Extra ssh options  (optional)
  CLS_FWD_PORT          Forward port for comm-layer-server       (default 40055)
  DR_FWD_PORT           Forward port for device-registry         (default 40058)
  GNMI_FWD_PORT         Forward port for comm-worker-gnmi        (default 40051)
  SUB_FWD_PORT          Forward port for comm-subscription-server (default 40056)
EOF
  exit 1
}

# --- SSH helper -----------------------------------------------------------

ssh_cmd() {
  local ssh_args=(-o ConnectTimeout=5 -o BatchMode=yes)
  if [[ -n "${K8S_SSH_KEY:-}" ]]; then
    ssh_args+=(-i "$K8S_SSH_KEY")
  fi
  if [[ -n "${K8S_SSH_OPTS:-}" ]]; then
    # shellcheck disable=SC2206
    ssh_args+=($K8S_SSH_OPTS)
  fi
  # Redirect stdin from /dev/null so SSH setup commands do not consume
  # piped input intended for the test-client binary.
  ssh "${ssh_args[@]}" "${K8S_SSH_USER}@${K8S_NODE_IP}" "$@" </dev/null
}

# --- Check status via SSH -------------------------------------------------

do_status() {
  echo "--- Service ---"
  ssh_cmd "kubectl get svc -n ${K8S_NAMESPACE} ${K8S_SVC_NAME} -o wide" 2>&1 || true
  echo ""
  echo "--- Pods ---"
  ssh_cmd "kubectl get pods -n ${K8S_NAMESPACE} -l app=${K8S_SVC_NAME} -o wide" 2>&1 || true
}

# --- Remote port-forward -------------------------------------------------

_resolve_pf_target() {
  local target="${K8S_PF_TARGET:-svc/${K8S_SVC_NAME}}"
  if [[ "$target" == "pod-selector" ]]; then
    echo "Resolving pod for app=${K8S_SVC_NAME} in ${K8S_NAMESPACE} ..." >&2
    target=$(ssh_cmd "kubectl get pods -n ${K8S_NAMESPACE} -l app=${K8S_SVC_NAME} \
      --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}'" 2>/dev/null)
    target="${target//\'/}"
    if [[ -z "$target" ]]; then
      echo "Error: no running pod found for app=${K8S_SVC_NAME}" >&2
      exit 1
    fi
    target="pod/${target}"
  fi
  echo "$target"
}

start_port_forward() {
  # Kill any leftover port-forward from a previous run
  echo "Checking for existing port-forward on ${K8S_NODE_IP}:${FWD_PORT} ..."
  ssh_cmd "fuser -k ${FWD_PORT}/tcp 2>/dev/null; true" 2>/dev/null || true
  sleep 0.5

  PF_TARGET=$(_resolve_pf_target)

  echo "Starting port-forward on ${K8S_NODE_IP}: :${FWD_PORT} -> ${PF_TARGET}:${K8S_SVC_PORT} ..."

  # Build SSH args with keepalive so the tunnel survives long benchmark runs.
  # NOTE: must NOT use $() command substitution here — that would orphan the ssh
  # child process when the subshell exits, killing the port-forward immediately.
  local _pf_ssh_args=(-o ConnectTimeout=5 -o BatchMode=yes
                      -o ServerAliveInterval=15 -o ServerAliveCountMax=10)
  if [[ -n "${K8S_SSH_KEY:-}" ]]; then _pf_ssh_args+=(-i "$K8S_SSH_KEY"); fi
  if [[ -n "${K8S_SSH_OPTS:-}" ]]; then
    # shellcheck disable=SC2206
    _pf_ssh_args+=($K8S_SSH_OPTS)
  fi
  ssh "${_pf_ssh_args[@]}" "${K8S_SSH_USER}@${K8S_NODE_IP}" \
    "kubectl port-forward -n ${K8S_NAMESPACE} ${PF_TARGET} \
     --address 0.0.0.0 ${FWD_PORT}:${K8S_SVC_PORT}" </dev/null &
  PF_SSH_PID=$!

  local attempts=0
  while ! nc -z -w 1 "$K8S_NODE_IP" "$FWD_PORT" 2>/dev/null; do
    sleep 0.5
    attempts=$((attempts + 1))
    if [[ $attempts -ge 20 ]]; then
      echo "Error: port-forward did not become ready after 10s" >&2
      stop_port_forward
      exit 1
    fi
    if ! kill -0 "$PF_SSH_PID" 2>/dev/null; then
      echo "Error: port-forward process exited unexpectedly" >&2
      echo "  Possible cause: port ${FWD_PORT} already in use on ${K8S_NODE_IP}" >&2
      echo "  Change *_FWD_PORT in k8s_test_env.local" >&2
      stop_port_forward
      exit 1
    fi
  done
  # Give kubectl port-forward a moment to complete the tunnel handshake.
  sleep 3
  echo "Port-forward ready (${K8S_NODE_IP}:${FWD_PORT})"

  # Watchdog: if the SSH process dies, restart it transparently.
  _pf_watchdog &
  PF_WATCHDOG_PID=$!
}

_pf_watchdog() {
  while true; do
    sleep 5
    if ! kill -0 "$PF_SSH_PID" 2>/dev/null; then
      echo "[port-forward watchdog] process died — restarting ..."
      ssh_cmd "fuser -k ${FWD_PORT}/tcp 2>/dev/null; true" 2>/dev/null || true
      sleep 1

      local _pf_ssh_args=(-o ConnectTimeout=5 -o BatchMode=yes
                          -o ServerAliveInterval=15 -o ServerAliveCountMax=10)
      if [[ -n "${K8S_SSH_KEY:-}" ]]; then _pf_ssh_args+=(-i "$K8S_SSH_KEY"); fi
      if [[ -n "${K8S_SSH_OPTS:-}" ]]; then
        # shellcheck disable=SC2206
        _pf_ssh_args+=($K8S_SSH_OPTS)
      fi
      ssh "${_pf_ssh_args[@]}" "${K8S_SSH_USER}@${K8S_NODE_IP}" \
        "kubectl port-forward -n ${K8S_NAMESPACE} ${PF_TARGET} \
         --address 0.0.0.0 ${FWD_PORT}:${K8S_SVC_PORT}" </dev/null &
      PF_SSH_PID=$!

      local w=0
      while ! nc -z -w 1 "$K8S_NODE_IP" "$FWD_PORT" 2>/dev/null; do
        sleep 0.5; w=$((w+1))
        if [[ $w -ge 20 ]]; then
          echo "[port-forward watchdog] restart failed — clients may see errors" >&2
          break
        fi
      done
      if nc -z -w 1 "$K8S_NODE_IP" "$FWD_PORT" 2>/dev/null; then
        sleep 1
        echo "[port-forward watchdog] restarted (pid=$PF_SSH_PID)"
      fi
    fi
  done
}

stop_port_forward() {
  # Stop the watchdog first so it does not restart what we are about to kill.
  if [[ -n "${PF_WATCHDOG_PID:-}" ]] && kill -0 "$PF_WATCHDOG_PID" 2>/dev/null; then
    kill "$PF_WATCHDOG_PID" 2>/dev/null || true
  fi
  if [[ -n "${PF_SSH_PID:-}" ]] && kill -0 "$PF_SSH_PID" 2>/dev/null; then
    kill "$PF_SSH_PID" 2>/dev/null || true
    wait "$PF_SSH_PID" 2>/dev/null || true
  fi
  # Kill the kubectl port-forward process on the jump host so it does not
  # outlive this script and block subsequent connections or interfere with
  # pod restarts.
  if [[ -n "${FWD_PORT:-}" && -n "${K8S_NODE_IP:-}" ]]; then
    echo "Cleaning up remote port-forward on ${K8S_NODE_IP}:${FWD_PORT} ..."
    ssh_cmd "fuser -k ${FWD_PORT}/tcp 2>/dev/null; true" 2>/dev/null || true
  fi
}

# --- Parse args -----------------------------------------------------------

CLIENT=""
FORCE_BUILD=false
DO_STATUS=false
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --client)  CLIENT="$2"; shift 2 ;;
    --build)   FORCE_BUILD=true; shift ;;
    --status)  DO_STATUS=true; shift ;;
    --)        shift; EXTRA_ARGS=("$@"); break ;;
    -h|--help) usage ;;
    *)         echo "Unknown arg: $1" >&2; usage ;;
  esac
done

if [[ -z "$CLIENT" ]]; then
  echo "Error: --client is required" >&2
  usage
fi

if [[ -z "${K8S_NODE_IP:-}" ]]; then
  echo "Error: K8S_NODE_IP not set. Run: source k8s_test_env.sh" >&2
  exit 1
fi

# --- Resolve client config ------------------------------------------------

case "$CLIENT" in
  comm-layer-server)
    REPO_DIR="${WORKSPACE_ROOT}/comm-layer-server"
    MAKE_TARGET="rpc_test_client"
    BINARY="bin/rpc_test_client"
    ADDR_FLAG="-addr"
    FWD_PORT="${CLS_FWD_PORT}"
    K8S_SVC_PORT="9001"
    K8S_NAMESPACE="nsp-communicator"
    K8S_SVC_NAME="comm-layer-server"
    ;;
  comm-layer-benchmark)
    REPO_DIR="${WORKSPACE_ROOT}/comm-layer-server"
    MAKE_TARGET="benchmark_client"
    BINARY="bin/benchmark_client"
    ADDR_FLAG="-server"
    FWD_PORT="${CLS_FWD_PORT}"
    K8S_SVC_PORT="9001"
    K8S_NAMESPACE="nsp-communicator"
    K8S_SVC_NAME="comm-layer-server"
    ;;
  device-registry)
    REPO_DIR="${WORKSPACE_ROOT}/device-registry"
    MAKE_TARGET="build-test-client"
    BINARY="bin/test-client"
    ADDR_FLAG="-server"
    FWD_PORT="${DR_FWD_PORT}"
    K8S_SVC_PORT="9001"
    K8S_NAMESPACE="nsp-device"
    K8S_SVC_NAME="device-registry"
    ;;
  comm-worker-gnmi)
    REPO_DIR="${WORKSPACE_ROOT}/comm-worker-gnmi-go"
    MAKE_TARGET="test_client"
    BINARY="bin/worker_test_client"
    ADDR_FLAG="-addr"
    FWD_PORT="${GNMI_FWD_PORT}"
    K8S_SVC_PORT="50051"
    K8S_NAMESPACE="nsp-communicator"
    K8S_SVC_NAME="comm-worker-gnmi"
    K8S_PF_TARGET="pod-selector"
    ;;
  comm-subscription-server)
    REPO_DIR="${WORKSPACE_ROOT}/comm-subscription-server"
    MAKE_TARGET="subscription_test_client"
    BINARY="bin/subscription_test_client"
    ADDR_FLAG="-addr"
    FWD_PORT="${SUB_FWD_PORT}"
    K8S_SVC_PORT="50056"
    K8S_NAMESPACE="nsp-communicator"
    K8S_SVC_NAME="comm-subscription-server"
    # K8s service resource is named comm-subscription-server-service in the kustomize base;
    # override the port-forward target so kubectl resolves the correct Service object.
    K8S_PF_TARGET="svc/comm-subscription-server-service"
    ;;
  *)
    echo "Error: unknown client '$CLIENT'" >&2
    echo "Supported: comm-layer-server, comm-layer-benchmark, device-registry, comm-worker-gnmi, comm-subscription-server" >&2
    exit 1
    ;;
esac

ADDR_VALUE="${K8S_NODE_IP}:${FWD_PORT}"

# --- Execute command ------------------------------------------------------

if [[ "$DO_STATUS" == true ]]; then
  do_status
  exit 0
fi

# Default: build + port-forward + connect
cd "$REPO_DIR"

needs_go_rebuild() {
  local bin="$1"
  shift
  [[ ! -x "$bin" ]] && return 0
  local dir
  for dir in "$@"; do
    if find "$dir" -name '*.go' -newer "$bin" -print -quit 2>/dev/null | grep -q .; then
      return 0
    fi
  done
  return 1
}

REBUILD=false
if [[ "$FORCE_BUILD" == true ]] || needs_go_rebuild "$BINARY" ./cmd ./internal; then
  REBUILD=true
fi

if [[ "$REBUILD" == true ]]; then
  echo "Building $CLIENT ($MAKE_TARGET) ..."
  make "$MAKE_TARGET"
fi

PF_SSH_PID=""
PF_WATCHDOG_PID=""
PF_TARGET=""

trap stop_port_forward EXIT
start_port_forward

echo "Connecting to $CLIENT at $ADDR_VALUE ..."
"./$BINARY" "$ADDR_FLAG" "$ADDR_VALUE" "${EXTRA_ARGS[@]}"
