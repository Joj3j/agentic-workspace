#!/usr/bin/env bash
# MDM log collection: Kubernetes kubectl cp, SCP, or local log directory.
#
# Environment file (optional):
#   MDM_LOG_ANALYZER_ENV=/path/to/mdm-log-analyzer.env
#   Or place mdm-log-analyzer.env in the skill root (parent of scripts/).
# Copy mdm-log-analyzer.env.example -> mdm-log-analyzer.env and set variables.
#
# Usage:
#   ./collect_logs.sh k8s [--namespace NS] [--pod POD] [--out DIR]
#   ./collect_logs.sh scp [USER@HOST:REMOTE_PATH] [--out DIR]
#   ./collect_logs.sh scp   # uses MDM_CUSTOMER_LOG_* from env
#   ./collect_logs.sh local [--out DIR]   # copies MDM_LOGS_LOCAL_DIR (MDM on this machine)
#   ./collect_logs.sh ssh [USER@IP:REMOTE_PATH] [--out DIR]
#       Pull logs over SSH via scp. Env: MDM_LOCAL_SERVER_IP, MDM_LOCAL_SSH_USER (default root),
#       MDM_LOCAL_REMOTE_LOG_PATH. Host: MDM_LOCAL_SERVER_IP or MDM_K8S_NODE_IP. Key auth if available; else password (no BatchMode).
#
# Environment:
#   MDM_LOG_ROOT, MDM_NAMESPACE, MDM_MDM_SERVER_POD
#   MDM_KUBECONFIG, MDM_K8S_CONTEXT, MDM_K8S_NODE_IP (same host as SSH pull when MDM_LOCAL_SERVER_IP unset)
#   MDM_LOGS_LOCAL_DIR, MDM_MDM_LOCAL (local logs / analysis hint)
#   MDM_CUSTOMER_* , MDM_SCP_PORT, MDM_K8S_LOGS_DOWNLOAD_DIR, MDM_CUSTOMER_LOGS_DOWNLOAD_DIR
#   MDM_LOCAL_SERVER_IP, MDM_LOCAL_SSH_USER, MDM_LOCAL_REMOTE_LOG_PATH, MDM_LOCAL_SSH_PORT, MDM_LOCAL_LOGS_DOWNLOAD_DIR
#   MDM_K8S_NODE_IP (default SSH host for ssh mode when MDM_LOCAL_SERVER_IP unset)
#
set -euo pipefail

MDM_LOG_ROOT="${MDM_LOG_ROOT:-/opt/nsp/mediation/log}"
MDM_NAMESPACE="${MDM_NAMESPACE:-nsp-psa-privileged}"
MDM_SCP_PORT="${MDM_SCP_PORT:-22}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

load_env_file() {
  local f="$1"
  if [[ -f "$f" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$f"
    set +a
    echo "Loaded env: $f"
  fi
}

load_env() {
  if [[ -n "${MDM_LOG_ANALYZER_ENV:-}" ]]; then
    load_env_file "$MDM_LOG_ANALYZER_ENV"
  elif [[ -f "$SKILL_ROOT/mdm-log-analyzer.env" ]]; then
    load_env_file "$SKILL_ROOT/mdm-log-analyzer.env"
  fi
}

load_env

# kubectl with optional kubeconfig + context (cluster selection)
kubectl_mdm() {
  if [[ -n "${MDM_KUBECONFIG:-}" ]]; then
    export KUBECONFIG="$MDM_KUBECONFIG"
  fi
  if [[ -n "${MDM_K8S_CONTEXT:-}" ]]; then
    command kubectl --context "$MDM_K8S_CONTEXT" "$@"
  else
    command kubectl "$@"
  fi
}

usage() {
  echo "Usage:"
  echo "  $0 k8s [--namespace NS] [--pod POD] [--out DIR]"
  echo "      kubectl cp from pod. Uses MDM_KUBECONFIG, MDM_K8S_CONTEXT if set."
  echo "      Default pod: \$MDM_MDM_SERVER_POD if set, else prompt."
  echo "      Default --out: \$MDM_K8S_LOGS_DOWNLOAD_DIR/mdm-k8s-<ts> if set, else ./mdm-logs-k8s-<ts>"
  echo "  $0 scp [USER@HOST:REMOTE_PATH] [--out DIR]"
  echo "      If USER@HOST:REMOTE_PATH omitted, uses MDM_SCP_USER, MDM_CUSTOMER_LOG_SERVER, MDM_CUSTOMER_REMOTE_LOG_PATH."
  echo "      Default --out: \$MDM_CUSTOMER_LOGS_DOWNLOAD_DIR/mdm-scp-<ts> if set, else ./mdm-logs-scp-<ts>"
  echo "  $0 local [--out DIR]"
  echo "      Copies \$MDM_LOGS_LOCAL_DIR into a timestamped folder (MDM logs already on this machine)."
  echo "  $0 ssh [USER@IP:REMOTE_PATH] [--out DIR]"
  echo "      scp -r over SSH (default user root@\$MDM_LOCAL_SERVER_IP). Key auth if configured; else password prompt."
  echo "      Default --out: \$MDM_LOCAL_LOGS_DOWNLOAD_DIR/mdm-ssh-<ts> or \$MDM_CUSTOMER_LOGS_DOWNLOAD_DIR, else ./mdm-logs-ssh-<ts>"
  echo "  $0 diag [--namespace NS] [--pod POD] [--container CTR] [--out DIR] [--queue QUEUE] [--all-queues]"
  echo "      Collect live diagnostics from a running mdm-server pod via app-console:"
  echo "        threads       -> <out>/threads-<ts>.txt"
  echo "        ne-list       -> <out>/ne-list-<ts>.txt"
  echo "        queues        -> <out>/queues-<ts>.txt"
  echo "        queue-dump    -> <out>/queue-dump-<QUEUE>-<ts>.txt  (default queue: MDM_DIAG_QUEUE or mdm-grpc-exec)"
  echo "      --all-queues: dump every queue listed in 'queues' output (in addition to the default)."
  echo "      --out defaults to the newest mdm-k8s-* dir under MDM_K8S_LOGS_DOWNLOAD_DIR, else ./mdm-diag-<ts>"
  exit 1
}

ts() { date +%Y%m%d-%H%M%S; }

collect_k8s() {
  local ns="$MDM_NAMESPACE"
  local pod=""
  local out=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --namespace) ns="$2"; shift 2 ;;
      --pod) pod="$2"; shift 2 ;;
      --out) out="$2"; shift 2 ;;
      *) echo "Unknown arg: $1"; usage ;;
    esac
  done

  if [[ -z "$out" ]]; then
    if [[ -n "${MDM_K8S_LOGS_DOWNLOAD_DIR:-}" ]]; then
      out="${MDM_K8S_LOGS_DOWNLOAD_DIR%/}/mdm-k8s-$(ts)"
    else
      out="./mdm-logs-k8s-$(ts)"
    fi
  fi
  mkdir -p "$out"

  if [[ -z "$pod" ]]; then
    if [[ -n "${MDM_MDM_SERVER_POD:-}" ]]; then
      pod="$MDM_MDM_SERVER_POD"
      echo "Using pod from env: $pod"
    else
      echo "Listing mdm-server pods in namespace $ns ..."
      kubectl_mdm get pods -n "$ns" -o name | grep -E 'pod/mdm-server-' || true
      read -r -p "Enter pod name (e.g. mdm-server-0): " pod
    fi
  fi

  if [[ -n "${MDM_K8S_NODE_IP:-}" ]]; then
    echo "Note: MDM_K8S_NODE_IP=${MDM_K8S_NODE_IP} (informational — ensure kubectl reaches the cluster)."
  fi

  echo "Copying ${ns}/${pod}:${MDM_LOG_ROOT} -> $out/"
  kubectl_mdm cp "${ns}/${pod}:${MDM_LOG_ROOT}" "$out/"

  echo "Done. Logs in: $out"
  echo "Tip: unzip rolled logs with: find \"$out\" -name '*.zip' -execdir unzip -o {} \\;"
}

collect_local() {
  local src="${MDM_LOGS_LOCAL_DIR:-}"
  local out=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --out) out="$2"; shift 2 ;;
      *) echo "Unknown arg: $1"; usage ;;
    esac
  done

  if [[ -z "$src" ]]; then
    echo "Error: set MDM_LOGS_LOCAL_DIR in mdm-log-analyzer.env (path to local MdmServer.log / mediation/log)."
    exit 1
  fi
  if [[ ! -d "$src" ]]; then
    echo "Error: MDM_LOGS_LOCAL_DIR is not a directory: $src"
    exit 1
  fi

  if [[ -z "$out" ]]; then
    if [[ -n "${MDM_K8S_LOGS_DOWNLOAD_DIR:-}" ]]; then
      out="${MDM_K8S_LOGS_DOWNLOAD_DIR%/}/mdm-local-$(ts)"
    elif [[ -n "${MDM_CUSTOMER_LOGS_DOWNLOAD_DIR:-}" ]]; then
      out="${MDM_CUSTOMER_LOGS_DOWNLOAD_DIR%/}/mdm-local-$(ts)"
    else
      out="./mdm-logs-local-$(ts)"
    fi
  fi
  mkdir -p "$out"
  # POSIX-friendly recursive copy of directory contents
  cp -R "$src/." "$out/"

  echo "Done. Local snapshot in: $out"
  echo "Analyze with: python scripts/parse_mdm_logs.py \"$out\" -o ..."
}

collect_scp() {
  local remote=""
  local out=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --out) out="$2"; shift 2 ;;
      *)
        if [[ -z "$remote" ]]; then remote="$1"; shift
        else echo "Unexpected: $1"; usage; fi
        ;;
    esac
  done

  if [[ -z "$remote" ]]; then
    if [[ -n "${MDM_CUSTOMER_LOG_SERVER:-}" && -n "${MDM_CUSTOMER_REMOTE_LOG_PATH:-}" ]]; then
      local u="${MDM_SCP_USER:-${USER:-root}}"
      remote="${u}@${MDM_CUSTOMER_LOG_SERVER}:${MDM_CUSTOMER_REMOTE_LOG_PATH}"
      echo "Using remote from env: $remote"
    else
      read -r -p "Enter SCP source (USER@IP:PATH): " remote
    fi
  fi

  if [[ -z "$out" ]]; then
    if [[ -n "${MDM_CUSTOMER_LOGS_DOWNLOAD_DIR:-}" ]]; then
      out="${MDM_CUSTOMER_LOGS_DOWNLOAD_DIR%/}/mdm-scp-$(ts)"
    else
      out="./mdm-logs-scp-$(ts)"
      echo "Note: MDM_CUSTOMER_LOGS_DOWNLOAD_DIR unset; using $out"
    fi
  fi
  mkdir -p "$out"

  local scp_opts=(-r)
  if [[ -n "${MDM_SCP_PORT:-}" && "$MDM_SCP_PORT" != "22" ]]; then
    scp_opts+=(-P "$MDM_SCP_PORT")
  fi

  echo "Running: scp ${scp_opts[*]} \"$remote\" \"$out/\""
  scp "${scp_opts[@]}" "$remote" "$out/"

  echo "Done. Logs in: $out"
}

# SSH to a "local" bare-metal / VM MDM host (root@IP typical). scp inherits ssh; no BatchMode so password works.
collect_ssh() {
  local remote=""
  local out=""

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --out) out="$2"; shift 2 ;;
      *)
        if [[ -z "$remote" ]]; then remote="$1"; shift
        else echo "Unexpected: $1"; usage; fi
        ;;
    esac
  done

  if [[ -z "$remote" ]]; then
    # Same host as K8s node/jump when MDM runs in-cluster: MDM_LOCAL_SERVER_IP overrides MDM_K8S_NODE_IP.
    local host="${MDM_LOCAL_SERVER_IP:-${MDM_K8S_NODE_IP:-}}"
    if [[ -z "$host" ]]; then
      read -r -p "Enter MDM log server IP or hostname (same as MDM_K8S_NODE_IP if pod-based): " host
    fi
    if [[ -z "$host" ]]; then
      echo "Error: set MDM_K8S_NODE_IP and/or MDM_LOCAL_SERVER_IP in mdm-log-analyzer.env, or pass USER@HOST:PATH."
      exit 1
    fi
    local u="${MDM_LOCAL_SSH_USER:-root}"
    local path="${MDM_LOCAL_REMOTE_LOG_PATH:-${MDM_LOG_ROOT}}"
    remote="${u}@${host}:${path}"
    echo "Using SSH pull: $remote"
  fi

  if [[ -z "$out" ]]; then
    if [[ -n "${MDM_LOCAL_LOGS_DOWNLOAD_DIR:-}" ]]; then
      out="${MDM_LOCAL_LOGS_DOWNLOAD_DIR%/}/mdm-ssh-$(ts)"
    elif [[ -n "${MDM_CUSTOMER_LOGS_DOWNLOAD_DIR:-}" ]]; then
      out="${MDM_CUSTOMER_LOGS_DOWNLOAD_DIR%/}/mdm-ssh-$(ts)"
    else
      out="./mdm-logs-ssh-$(ts)"
    fi
  fi
  mkdir -p "$out"

  local port="${MDM_LOCAL_SSH_PORT:-${MDM_SCP_PORT:-22}}"
  local scp_opts=(-r -o "PreferredAuthentications=publickey,keyboard-interactive,password")
  # Intentionally no BatchMode=yes so OpenSSH can prompt for password when keys are missing/unauthorized.

  if [[ "$port" != "22" ]]; then
    scp_opts+=(-P "$port")
  fi

  echo "Connecting: if your key is loaded and authorized on the server, no password is needed."
  echo "Otherwise you will be prompted for the SSH password (run from an interactive terminal)."
  echo "Running: scp ${scp_opts[*]} \"$remote\" \"$out/\""
  scp "${scp_opts[@]}" "$remote" "$out/"

  echo "Done. Logs in: $out"
}

collect_diag() {
  local ns="${MDM_NAMESPACE:-nsp-psa-privileged}"
  local pod="${MDM_MDM_SERVER_POD:-}"
  local ctr="${MDM_MDM_SERVER_CONTAINER:-cn-nsp-mdm-server}"
  local queue="${MDM_DIAG_QUEUE:-mdm-grpc-exec}"
  local out=""
  local all_queues=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --namespace)  ns="$2";    shift 2 ;;
      --pod)        pod="$2";   shift 2 ;;
      --container)  ctr="$2";   shift 2 ;;
      --out)        out="$2";   shift 2 ;;
      --queue)      queue="$2"; shift 2 ;;
      --all-queues) all_queues=1; shift ;;
      *) echo "Unknown arg: $1"; usage ;;
    esac
  done

  # Resolve pod name
  if [[ -z "$pod" ]]; then
    echo "Listing mdm-server pods in namespace $ns ..."
    kubectl_mdm get pods -n "$ns" -o name | grep -E 'pod/mdm-server-' || true
    read -r -p "Enter pod name (e.g. mdm-server-0): " pod
    [[ -z "$pod" ]] && { echo "Error: pod name required."; exit 1; }
  fi

  # Resolve output dir — default to newest mdm-k8s-* snapshot if available
  if [[ -z "$out" ]]; then
    local base_dir="${MDM_K8S_LOGS_DOWNLOAD_DIR:-.}"
    local newest
    newest=$(ls -dt "${base_dir}"/mdm-k8s-* 2>/dev/null | head -1 || true)
    if [[ -n "$newest" && -d "$newest" ]]; then
      out="$newest"
      echo "Using existing snapshot dir for diagnostics: $out"
    else
      out="./mdm-diag-$(ts)"
      echo "No mdm-k8s-* snapshot found; writing to: $out"
    fi
  fi
  mkdir -p "$out"

  local t; t=$(ts)
  echo "=== MDM live diagnostics: pod=${ns}/${pod}, container=${ctr} ==="

  # 1) Thread dump
  echo "[1/4] Collecting thread dump..."
  kubectl_mdm exec -i -n "$ns" "$pod" -c "$ctr" -- app-console threads \
    > "${out}/threads-${t}.txt" 2>&1 || echo "WARN: thread dump failed (exit $?)"
  echo "      -> ${out}/threads-${t}.txt"

  # 2) NE list
  echo "[2/4] Collecting NE list..."
  kubectl_mdm exec -i -n "$ns" "$pod" -c "$ctr" -- app-console ne-list \
    > "${out}/ne-list-${t}.txt" 2>&1 || echo "WARN: ne-list failed (exit $?)"
  echo "      -> ${out}/ne-list-${t}.txt"

  # 3) All-queue summary
  echo "[3/4] Collecting queue summary..."
  kubectl_mdm exec -i -n "$ns" "$pod" -c "$ctr" -- app-console queues \
    > "${out}/queues-${t}.txt" 2>&1 || echo "WARN: queues failed (exit $?)"
  echo "      -> ${out}/queues-${t}.txt"

  # 4) Queue detail dump — default queue + optional all-queues
  _dump_queue() {
    local q="$1"
    local pod_tmp="/tmp/${q}-dump.txt"
    echo "      queue-dump: $q -> ${pod_tmp} (in pod) -> ${out}/queue-dump-${q}-${t}.txt"
    kubectl_mdm exec -i -n "$ns" "$pod" -c "$ctr" -- \
      app-console "queue-dump ${q} ${pod_tmp}" 2>&1 || {
        echo "      WARN: queue-dump ${q} failed (exit $?)"; return
      }
    kubectl_mdm cp "${ns}/${pod}:${pod_tmp}" "${out}/queue-dump-${q}-${t}.txt" -c "$ctr" 2>&1 \
      || echo "      WARN: kubectl cp of ${pod_tmp} failed (exit $?)"
  }

  echo "[4/4] Collecting queue dump(s)..."
  _dump_queue "$queue"

  if [[ "$all_queues" -eq 1 && -s "${out}/queues-${t}.txt" ]]; then
    echo "      --all-queues: parsing queue names from queues-${t}.txt ..."
    # Extract queue names — adjust awk field if the format differs
    while IFS= read -r qname; do
      [[ "$qname" == "$queue" ]] && continue  # already dumped above
      [[ -n "$qname" ]] && _dump_queue "$qname"
    done < <(awk 'NR>1 && $1!="" {print $1}' "${out}/queues-${t}.txt" 2>/dev/null)
  fi

  echo ""
  echo "Done. Diagnostics in: $out"
  echo "Files:"
  ls -lh "${out}/threads-${t}.txt" "${out}/ne-list-${t}.txt" \
         "${out}/queues-${t}.txt" "${out}"/queue-dump-*-"${t}".txt 2>/dev/null || true
  echo ""
  echo "Pass to pipeline:  --threaddump ${out}/threads-${t}.txt"
}

main() {
  [[ $# -lt 1 ]] && usage
  local mode="$1"
  shift
  case "$mode" in
    k8s)  collect_k8s  "$@" ;;
    scp)  collect_scp  "$@" ;;
    local) collect_local "$@" ;;
    ssh)  collect_ssh  "$@" ;;
    diag) collect_diag "$@" ;;
    *) usage ;;
  esac
}

main "$@"
