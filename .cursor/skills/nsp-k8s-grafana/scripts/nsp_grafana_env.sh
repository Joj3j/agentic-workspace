#!/usr/bin/env bash
# NSP Grafana environment configuration.
# Copy to nsp_grafana_env.local (gitignored) and set values, then: source nsp_grafana_env.sh
# If .local file exists it is sourced automatically.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCAL_ENV="${SCRIPT_DIR}/nsp_grafana_env.local"
[[ -f "$LOCAL_ENV" ]] && source "$LOCAL_ENV"

# ── NSP Gateway ──────────────────────────────────────────────────────────────
# Required: NSP REST Gateway host (no scheme, no trailing slash).
# Examples: 100.127.237.96   or   nsp.example.com
export NSP_GATEWAY="${NSP_GATEWAY:-}"

# ── Credentials ──────────────────────────────────────────────────────────────
export NSP_USER="${NSP_USER:-admin}"
export NSP_PASSWORD="${NSP_PASSWORD:-NokiaNsp1!}"

# ── Grafana ──────────────────────────────────────────────────────────────────
# Grafana is served behind the NSP gateway at /grafana/.
# Full URL is built as: ${NSP_HTTPS_SCHEME}://${NSP_GATEWAY}/grafana
export GRAFANA_SUBPATH="${GRAFANA_SUBPATH:-/grafana}"

# Optional: Grafana API key / service-account token. If set, preferred over user/pass.
export GRAFANA_API_KEY="${GRAFANA_API_KEY:-}"

# ── TLS / Scheme ─────────────────────────────────────────────────────────────
export NSP_HTTPS_SCHEME="${NSP_HTTPS_SCHEME:-https}"

# 1 = verify TLS (default). 0 = allow self-signed / corporate MITM.
export NSP_VERIFY_TLS="${NSP_VERIFY_TLS:-0}"

# ── Kubernetes ───────────────────────────────────────────────────────────────
export NSP_NAMESPACE="${NSP_NAMESPACE:-nsp-psa-privileged}"
# Optional: specific kube context. Leave empty to use current context.
export NSP_KUBE_CONTEXT="${NSP_KUBE_CONTEXT:-}"

# ── Derived (do not edit) ────────────────────────────────────────────────────
export GRAFANA_URL="${NSP_HTTPS_SCHEME}://${NSP_GATEWAY}${GRAFANA_SUBPATH}"

# Validate
if [[ -z "$NSP_GATEWAY" ]]; then
  echo "WARNING: NSP_GATEWAY is not set. Export it or create ${LOCAL_ENV}" >&2
fi
