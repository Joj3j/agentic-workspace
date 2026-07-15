#!/usr/bin/env bash
# NSP Kubernetes health check.
# Usage: source nsp_grafana_env.sh && bash nsp_k8s_check.sh [--wide]
set -euo pipefail

NS="${NSP_NAMESPACE:-nsp-psa-privileged}"
CTX="${NSP_KUBE_CONTEXT:-}"
WIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --namespace|-n) NS="$2"; shift 2 ;;
    --context)      CTX="$2"; shift 2 ;;
    --wide)         WIDE="-o wide"; shift ;;
    -h|--help)      echo "Usage: $0 [--namespace NS] [--context CTX] [--wide]"; exit 0 ;;
    *)              echo "Unknown: $1"; exit 1 ;;
  esac
done

KC="kubectl"
[[ -n "$CTX" ]] && KC="kubectl --context $CTX"

hdr() { printf '\n\033[1;36m=== %s ===\033[0m\n' "$1"; }

hdr "Cluster Info"
$KC cluster-info 2>&1 | head -5

hdr "Pods in $NS"
$KC get pods -n "$NS" $WIDE --sort-by=.metadata.name 2>&1

hdr "Unhealthy Pods"
$KC get pods -n "$NS" -o json 2>/dev/null | python3 -c "
import json,sys
data=json.load(sys.stdin)
found=False
for pod in data.get('items',[]):
    name=pod['metadata']['name']
    phase=pod.get('status',{}).get('phase','Unknown')
    for cs in pod.get('status',{}).get('containerStatuses',[]):
        r=cs.get('restartCount',0); rdy=cs.get('ready',False)
        if phase!='Running' or not rdy or r>3:
            print(f'  WARN  {name:50s}  phase={phase}  ready={rdy}  restarts={r}')
            found=True
if not found: print('  All pods healthy.')
" 2>&1

hdr "Services in $NS"
$KC get svc -n "$NS" $WIDE 2>&1

hdr "StatefulSets in $NS"
$KC get statefulsets -n "$NS" $WIDE 2>&1 || echo "  (none)"

hdr "Grafana (searching all namespaces)"
$KC get svc -A 2>/dev/null | grep -i grafana || echo "  No Grafana service found."

hdr "Grafana Ingress"
($KC get ingress -A 2>/dev/null || $KC get route -A 2>/dev/null) | grep -i grafana \
  || echo "  No ingress/route for Grafana found."

if [[ -n "${NSP_GATEWAY:-}" ]]; then
  hdr "NSP Gateway Grafana (env-based)"
  echo "  URL: ${NSP_HTTPS_SCHEME:-https}://${NSP_GATEWAY}${GRAFANA_SUBPATH:-/grafana}"
  echo "  Test: python scripts/grafana_api.py health"
fi

echo ""
echo "Done."
