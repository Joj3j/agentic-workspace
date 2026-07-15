---
name: nsp-k8s-grafana
description: >-
  Connects to Nokia NSP Kubernetes deployments and Grafana dashboards via the
  NSP gateway (/grafana/ subpath). Loads dashboard JSON created in the
  workspace, validates PromQL counters against live Prometheus, and queries
  metrics for workspace services (comm-worker-gnmi, comm-layer-server,
  device-registry, comm-dispatcher, etc.). Server details come from
  nsp_grafana_env.local. Use when loading or checking Grafana dashboards,
  querying Prometheus metrics, or troubleshooting NSP deployment via Grafana.
---

# NSP K8s & Grafana Connector

## When to apply

- Load a dashboard JSON file (created in the workspace) into Grafana
- Download/export any Grafana dashboard from the NSP gateway
- Review dashboard JSON for counter issues (hardcoded pods, missing rates, whitespace)
- Fix issues and re-upload the corrected dashboard
- Test that all PromQL counters actually return data
- Query Prometheus metrics for workspace services
- Health-check NSP K8s pods and Grafana API

## Environment setup

Server details live in `scripts/nsp_grafana_env.local` (gitignored). Edit that file with
the target NSP gateway IP, then source the env before running any script:

```bash
# Edit once per target server:
#   scripts/nsp_grafana_env.local  ← set NSP_GATEWAY (and optionally credentials)

source scripts/nsp_grafana_env.sh   # loads .local automatically
```

Variables set by `nsp_grafana_env.sh`:

| Variable | Default | Purpose |
|----------|---------|---------|
| `NSP_GATEWAY` | (required — set in .local) | NSP gateway host |
| `NSP_USER` | `admin` | Grafana user |
| `NSP_PASSWORD` | (set in `nsp_grafana_env.local`) | Grafana password |
| `GRAFANA_API_KEY` | — | Bearer token; overrides user/pass if set |
| `NSP_VERIFY_TLS` | `0` | `0` = skip TLS verify, `1` = strict |
| `NSP_NAMESPACE` | `nsp-psa-privileged` | K8s namespace |
| `GRAFANA_URL` | built from gateway | Full Grafana base URL (auto-derived) |

## Typical workflow: create in workspace, load to Grafana

```bash
source scripts/nsp_grafana_env.sh

# 1. Load a new dashboard JSON created in the workspace
python scripts/grafana_api.py dashboards import /path/to/my-dashboard.json --overwrite

# 2. Verify it loaded and get the UID
python scripts/grafana_api.py dashboards search "my dashboard name"

# 3. Test all PromQL counters return data
python scripts/grafana_api.py test-counters <uid>

# 4. Open in browser
python scripts/grafana_api.py open <uid>
```

## All commands

```bash
source scripts/nsp_grafana_env.sh

# Health check
python scripts/grafana_api.py health

# List / search dashboards
python scripts/grafana_api.py dashboards list
python scripts/grafana_api.py dashboards search "gnmi"

# Get dashboard details and panel list
python scripts/grafana_api.py dashboards get <uid>

# Export dashboard to file
python scripts/grafana_api.py dashboards export <uid> -o dashboard.json

# Import (create or overwrite) dashboard
python scripts/grafana_api.py dashboards import dashboard.json --overwrite

# Diff live vs local file
python scripts/grafana_api.py dashboards diff <uid> dashboard.json

# List panels with IDs and expressions
python scripts/grafana_api.py panels list <uid>

# Test all PromQL counters in a dashboard (live UID or local file)
python scripts/grafana_api.py test-counters <uid>
python scripts/grafana_api.py test-counters dashboard.json

# One-off Prometheus queries
python scripts/grafana_api.py query 'grpc_server_handled_total{pod=~"comm-worker-gnmi.*"}'
python scripts/grafana_api.py query-range \
  'rate(grpc_server_handled_total{pod=~"comm-worker-gnmi.*"}[2m])' --start 1h

# Print browser URL
python scripts/grafana_api.py open <uid>

# K8s health (pods, restarts)
bash scripts/nsp_k8s_check.sh
```

## Download → review → fix → re-upload

```bash
# Download
python scripts/grafana_api.py dashboards export <uid> -o dashboard.json

# Offline review (hardcoded pods, whitespace, deprecated types, missing $instance)
python scripts/dashboard_review.py dashboard.json

# Auto-fix and write to new file
python scripts/dashboard_review.py dashboard.json --fix -o dashboard-fixed.json

# Validate all counters against live Prometheus
python scripts/grafana_api.py test-counters dashboard-fixed.json

# Upload fixed version
python scripts/grafana_api.py dashboards import dashboard-fixed.json --overwrite
```

## Workspace service metrics

Use these label patterns when writing PromQL in dashboards:

| Service | Pod label pattern | Key metric prefixes |
|---------|-------------------|---------------------|
| comm-worker-gnmi | `pod=~"comm-worker-gnmi.*"` | `grpc_server_*`, `gnmi_*` |
| comm-worker-netconf | `pod=~"comm-worker-netconf.*"` | `grpc_server_*`, `netconf_*` |
| comm-layer-server | `pod=~"comm-layer-server.*"` | `grpc_server_*`, `rabbitmq_*` |
| comm-dispatcher | `pod=~"comm-dispatcher.*"` | `grpc_server_*`, `dispatch_*` |
| device-registry | `pod=~"device-registry.*"` | `grpc_server_*`, `etcd_*` |
| comm-subscription-server | `pod=~"comm-subscription-server.*"` | `grpc_server_*` |
| nsp-schema-server | `pod=~"nsp-schema-server.*"` | `grpc_server_*`, `schema_*` |
| discovery-service | `pod=~"discovery-service.*"` | `grpc_server_*` |

**Common gRPC counters (all Go services):**

```promql
# Request rate by method
rate(grpc_server_handled_total{pod=~"<pattern>"}[2m])

# Error rate
rate(grpc_server_handled_total{pod=~"<pattern>",grpc_code!="OK"}[2m])

# Latency p99
histogram_quantile(0.99, rate(grpc_server_handling_seconds_bucket{pod=~"<pattern>"}[5m]))

# In-flight RPCs
grpc_server_started_total{pod=~"<pattern>"} - grpc_server_handled_total{pod=~"<pattern>"}
```

**Container resource counters:**

```promql
rate(container_cpu_usage_seconds_total{container="<name>",pod=~"<pattern>"}[2m])
container_memory_usage_bytes{container="<name>",pod=~"<pattern>"}
kube_pod_container_status_restarts_total{pod=~"<pattern>"}
```

## Common dashboard issues

| Issue | Fix |
|-------|-----|
| Hardcoded `pod="<name>-0"` | Change to `pod=~"<name>-$instance"` |
| Leading/trailing whitespace in PromQL | Trim |
| Raw counters without `rate()` | Add rate panel alongside raw total |
| Deprecated `graph` panel type | Upgrade to `timeseries` |
| Missing `$instance` template variable | Add for pod selection |

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/nsp_grafana_env.sh` | Env loader — source this first; reads `.local` automatically |
| `scripts/nsp_grafana_env.local` | Local overrides (gitignored) — set `NSP_GATEWAY` here |
| `scripts/grafana_api.py` | Full Grafana API client — import, export, diff, query, test-counters |
| `scripts/dashboard_review.py` | Offline dashboard JSON review and auto-fix |
| `scripts/nsp_k8s_check.sh` | K8s namespace health: pods, services, restarts |
