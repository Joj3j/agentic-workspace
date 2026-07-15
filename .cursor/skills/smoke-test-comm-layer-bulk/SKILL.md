---
name: smoke-test-comm-layer-bulk
description: >-
  Run a reduced-scale async bulk write smoke test for comm-layer-server against
  the K8s cluster using cmd/benchmark_client (asyncUpdateHierarchyObjects +
  receiveEventDeploymentNotifications). Includes **Get NE**: query device-registry
  (`GetNeEntries` via test_client `-cmd get-ne-entries`) over the same
  k8s-test-client tunnel, with optional `-ne-type`, `-ne-version`, and
  `-protocol` filters, then wire IDs into `SMOKE_NES`. For epipe/srl smoke,
  `-nes` is **required** (no lab defaults in the binary). Async writes per NE
  (`-epipes`) equal the number of unique services created per NE. Service names
  use a stable prefix (`-epipe-prefix`, default `"ne"`) so cleanup is exact.
  **Epipe mode** (default) uses `bulkbench.BuildSRBulkPayload` — **1 unique
  epipe + 1 router interface per write** so writes/NE == unique services in MDC.
  **SRL smoke** (`-mode srl`) uses `bulkbench.BuildSRLBulkPayload` per write (two
  interfaces per RPC; same shape as `rpc_test_client` SRL bulk). **Bulk mode**
  (`-mode bulk`) drives SR1K + SRL payloads from `cmd/rpc_test_client/bulkbench`
  (same shapes as `rpc_test_client` bulk paths): configurable entries per SR NE,
  SRL iteration count, **remove** cleanup for SR, deploy tracking, inferred
  **bulk size** stats, and **consecutive-failure stop**. After the run the agent
  MUST produce a per-NE summary table (see "Post-run summary") for epipe smoke.
  Use when asked to smoke test comm-layer-server bulk write, discover NEs for a
  smoke, run SR/SRL scale loads, or run a small async bulk run against the cluster.
---

# Smoke Test — comm-layer-server Async Bulk Write

Runs `cmd/benchmark_client` against the **comm-layer-server** pod in K8s. The
client fires `AsyncUpdateHierarchyObjects` RPCs per NE in parallel, registers a
`ReceiveEventDeploymentNotifications` stream per `clientId`, and waits for the
terminal `AsyncDeployResponseInfo` per ticket. Pass/fail is determined by
per-ticket success and aggregate wall clock.

Reuses `k8s-test-client` (SSH + kubectl port-forward) — the wrapper now
recognizes the `comm-layer-benchmark` client which port-forwards
`pod:9001 -> jump:${CLS_FWD_PORT}` and runs `bin/benchmark_client -server …`.

## Default smoke scale (configurable)

| Parameter | Default (smoke) | Full target | Override |
|-----------|-----------------|-------------|----------|
| NEs | 2 | 80 | `SMOKE_NES` (comma list) or `-nes` |
| Services per NE (`-epipes`) | 50 | 4 000 | `SMOKE_EPIPES` or `-epipes` |
| Service name prefix (`-epipe-prefix`) | `ne` | any stable string | `SMOKE_EPIPE_PREFIX` or `-epipe-prefix` |
| Read checkpoint interval | 0 (off) | 50 | `SMOKE_READ_INTERVAL` or `-read-interval` |
| Client prefix | `smoke` | `benchmark` | `SMOKE_CLIENT_PREFIX` or `-client-prefix` |

At smoke defaults: 2 NEs × **50 writes** each → **50 unique services per NE**
(e.g. `ne0-epipe-1`…`ne0-epipe-50`). Each write is one
`AsyncUpdateHierarchyObjects` with exactly **1 epipe + 1 router interface**.
`-epipes N` == unique services visible in MDC per NE after the run.
Expected wall clock on a healthy cluster: **under ~90 s**.

> **NE selection:** Prefer **Get NE** (below) so `SMOKE_NES` matches what
> device-registry already routes. NE IDs are passed verbatim in the gRPC
> request. You may still use a fixed pair when you already know they are
> registered.

## Service naming and cleanup contract

Service names follow the pattern **`<prefix><neIdx>-epipe-<id>`** and
**`<prefix><neIdx>-iface-<id>`**, where:

- `<prefix>` is the value of `-epipe-prefix` (default `"ne"`).
- `<neIdx>` is the 0-based index of the NE in the `-nes` list.
- `<id>` = `neIdx × 10 000 + iter + 1` (unique per write, no gaps).

Because the prefix is stable and deterministic, cleanup always targets the
exact set created in a run:

```bash
# create (50 unique services per NE, prefix "smoke")
-nes "..." -epipes 50 -epipe-prefix smoke

# cleanup (removes exactly those 50 services per NE)
-nes "..." -epipes 50 -epipe-prefix smoke -cleanup
```

Use a **different prefix per logical run** (e.g. `smoke`, `bench`, `load`) to
keep footprints from different runs separated and independently cleanable.

### Legacy cleanup

Older benchmark runs (before this naming scheme) left services named
`bulk-epipe-12501..12503`. Remove them once with:

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -nes "<ne1>,<ne2>,..." \
  -client-prefix smoke \
  -cleanup-legacy
```

## Concurrency layout

Per NE goroutine in the benchmark client:

1. Opens a `ReceiveEventDeploymentNotifications` stream with
   `clientId = <client-prefix>-<neId>`.
2. Loops **`-epipes`** times, issuing `AsyncUpdateHierarchyObjects` each with
   `bulkbench.BuildSRBulkPayload(prefix, neIdx, iter, "create")` (**`-mode epipe`**,
   1 unique epipe per call) or `bulkbench.BuildSRLBulkPayload(srlStartIter+iter)`
   (**`-mode srl`**, 2 interfaces per call).
3. Counts notifications from the deploy stream; finishes when total
   `successes + failures == submissions` (dynamic wait budget from submission count).

Across NEs the loops run **in parallel** (one goroutine per NE).

## `benchmark_client` modes

| `-mode` | Meaning |
|---------|---------|
| `epipe` (default) | SR smoke: **1 unique epipe + 1 router interface per write**. Service names `<prefix><neIdx>-epipe-<id>`. `-cleanup` removes the exact range; `-cleanup-legacy` removes old `bulk-epipe-12501..12503`. |
| `srl` | SRL smoke: each write `BuildSRLBulkPayload(srlStartIter+i)` (two `ethernet-1/*` interfaces per RPC). **`-nes` required** (comma SRL NE IDs); `-cleanup` is a no-op. |
| `bulk` | **SR + SRL lab payloads** from `cmd/rpc_test_client/bulkbench`: SR uses `ne1k-epipe-*` + router ifaces (service IDs from `SR1KBase`); SRL rotates `ethernet-1/1`…`1/32` pairs. SR **delete** via `-sr-op delete`. |

### Epipe mode — key flags

| Flag | Role |
|------|------|
| `-nes` | Comma-separated SR NE IDs (required). |
| `-epipes N` | Writes per NE = unique services created per NE (default 250). |
| `-epipe-prefix P` | Service name prefix (default `"ne"`). Use a stable, run-specific value. |
| `-client-prefix P` | gRPC clientId prefix (default `"benchmark"`). |
| `-cleanup` | Delete all services created in this run (same `-nes`, `-epipes`, `-epipe-prefix`). |
| `-cleanup-legacy` | One-time: remove `bulk-epipe-12501..12503` left by older runs. |
| `-read-interval N` | Read checkpoint every N submissions (0 = off). |

### Bulk mode — main flags

| Flag | Role |
|------|------|
| `-sr-entries-per-ne N` | SR: `N` epipe+iface **per NE** (0 = skip SR). Align `N` with `-batch` (`N % batch == 0`). |
| `-srl-iters M` | SRL: `M` total `AsyncUpdateHierarchyObjects` calls, round-robin on `-srl-ne` (0 = skip SRL). |
| `-batch` | SR: objects per ticket (default 20). More tickets per NE → larger bulk merge opportunity (`-sr-parallel 0` fans out all). |
| `-sr-parallel` | SR: max concurrent batch RPCs **per NE** (0 = all batches at once for max bulking). |
| `-srl-parallel` | SRL: max in-flight submits (0 = all `srl-iters` at once). |
| `-sr-op` | SR operation: `create` or `delete` (same SR1K IDs); `remove` is an alias for `delete`. |
| `-sr-ne`, `-srl-ne` | Comma NE lists for **bulk** mode only; **required** when `-sr-entries-per-ne` or `-srl-iters` is non-zero. Use **Get NE** to populate. |
| `-client-pool` | SRL: deploy-notification client pool size (default 5). |
| `-bulk-cluster-ms` | Window for **BulkSizeTracker** inference (default 100). |
| `-max-fail-streak` | After **N** consecutive submit/deploy failures, stop launching new RPCs (0 = off). |
| `-deadline-min` | Parent context for the whole bulk run (default 300). |
| `-deploy-wait-sr-min` / `-deploy-wait-srl-min` | Per-ticket wait caps (default 10 / 4 minutes). |
| `-srl-start-iter` | Seed for `BuildSRLBulkPayload` rotation (default 0). |

SR and SRL legs run **in parallel** when both counts are non-zero. Each leg
prints **estimated bulkSize** (min / max / avg / clusters) from notification
completion clustering.

### Bulk mode — examples

Create **6000** epipe+iface entries per SR NE and **1000** SRL interface batches
(max fan-out on both legs):

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -mode bulk \
  -sr-entries-per-ne 6000 \
  -srl-iters 1000 \
  -batch 20 \
  -sr-parallel 0 \
  -srl-parallel 0 \
  -client-prefix smoke
```

**Delete SR** footprint created above:

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -mode bulk \
  -sr-entries-per-ne 6000 \
  -sr-op delete \
  -batch 20 \
  -sr-parallel 0 \
  -srl-iters 0 \
  -client-prefix smoke
```

**Custom NE pools** (e.g. after Get NE), still max bulking:

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -mode bulk \
  -sr-ne "9.168.96.101,9.168.96.118,9.168.96.158,9.168.96.186" \
  -srl-ne "92.4.201.116,92.3.202.71,92.2.197.18,92.1.203.111" \
  -sr-entries-per-ne 2000 \
  -srl-iters 200 \
  -batch 20 \
  -sr-parallel 0 \
  -max-fail-streak 10 \
  -client-prefix smoke
```

## Prerequisites

1. `k8s-test-client` env configured.
2. `source /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client/k8s_test_env.sh`
3. `export WORKSPACE_ROOT=/home/joji/Go`
4. `comm-layer-server` deployed in `nsp-communicator` with **bulking enabled**
   (`configwrite.bulking.enabled=true`). Confirm with `--status` below.
5. (Optional) **device-registry** reachable for Get NE — same jump host;
   confirm with `bash k8s_run_test_client.sh --status --client device-registry`.

## Get NE (device-registry)

**Purpose:** Before scaling or when the user asks for cluster NEs, call
**device-registry** `RegistryService.GetNeEntries` in non-interactive mode
(`runNonInteractive` in `device-registry/cmd/test_client.go`) so the bulk smoke
targets NEs the registry actually knows.

**Transport:** Same `k8s-test-client` env as the benchmark: SSH to
`${K8S_NODE_IP}`, `kubectl port-forward` **device-registry** on
`jump:${DR_FWD_PORT}` (default **40058**) → pod gRPC. Set
`export WORKSPACE_ROOT=/home/joji/Go` so `k8s_run_test_client.sh` resolves the
`device-registry` repo.

### Get NE — flags and optional env

| Filter / output | CLI flag | Example | Notes |
|-----------------|----------|---------|-------|
| NE type | `-ne-type` | `-ne-type SR-7750` | Exact match per registry (e.g. `7250-IXR-SRL`, `7730-SXR-SRL`) |
| NE version | `-ne-version` | `-ne-version 24.10.R4` | Combine with `-ne-type` to narrow further |
| Protocol | `-protocol` | `-protocol gnmi` or `-protocol netconf` | Values: `gnmi` \| `netconf` (omit for all) |
| Output | `-format` | `text` (default), `ids`, `tsv`, `json` | **`tsv`** for scripted `SMOKE_NES` (see wire recipe); `ids` is fine for copy-paste |

Optional convenience (shell only; not read by `test_client`):

```bash
export SMOKE_NE_TYPE=""        # e.g. SR-7750
export SMOKE_NE_VERSION=""     # e.g. 24.10.R4
export SMOKE_NE_PROTOCOL=""    # gnmi or netconf
```

### Get NE — run (workspace script)

```bash
cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
export WORKSPACE_ROOT=/home/joji/Go

# All NEs, machine-readable (TSV header + rows)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries \
  -format tsv

# Refined list: SRL family only (example)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries -ne-type 7250-IXR-SRL -format tsv

# gNMI-capable NEs only (example)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries -protocol gnmi -format tsv

# Combine filters (example)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries -ne-type SR-7750 -ne-version 24.10.R4 -format ids
```

### Get NE — shortcut from device-registry repo

```bash
cd /home/joji/Go/device-registry
export WORKSPACE_ROOT=/home/joji/Go
./bin/k8s_dr_test.sh -- \
  -cmd get-ne-entries -ne-type SR-7750 -format tsv
```

(`bin/k8s_dr_test.sh` sources the same `k8s_test_env.sh` and invokes
`k8s_run_test_client.sh --client device-registry`.)

### Get NE — wire list into `SMOKE_NES`

`k8s_run_test_client.sh` prints status lines to stdout before the binary runs, so
**do not** pipe raw `-format ids` straight into `paste` without filtering. Prefer
**`-format tsv`** and keep only real data rows (four tab-separated columns; skip
the `ne_id` header):

```bash
export SMOKE_NES="$(
  cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
  source k8s_test_env.sh
  export WORKSPACE_ROOT=/home/joji/Go
  bash k8s_run_test_client.sh --client device-registry -- \
    -cmd get-ne-entries \
    ${SMOKE_NE_TYPE:+-ne-type "$SMOKE_NE_TYPE"} \
    ${SMOKE_NE_VERSION:+-ne-version "$SMOKE_NE_VERSION"} \
    ${SMOKE_NE_PROTOCOL:+-protocol "$SMOKE_NE_PROTOCOL"} \
    -format tsv 2>&1 | awk -F'\t' 'NF==4 && $1!="ne_id" {print $1}' | paste -sd, -
)"
```

For a **fixed smoke pair** (two SRL NEs), you can still set `SMOKE_NES` by hand
once Get NE confirms those IDs exist.

### Get NE — agent behavior

When the user asks to **get NEs first**, **discover NEs**, or **filter by type /
protocol** before a bulk smoke: run Get NE (at least once with `-format tsv` or
`ids`), present the table or ID list, then set `SMOKE_NES` (or a subset) for
steps 3–4.

### Get NE — SSH / known_hosts

If SSH fails with `Host key verification failed` or `known_hosts` permission
errors from the agent environment, retry with e.g.
`K8S_SSH_OPTS="-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/k8s_dr_known_hosts"`
for that invocation, or add the same to `k8s_test_env.local`.

## Agent steps

### 0 — Get NE list (when NEs are unknown or filters are requested)

Run **Get NE** (section above). Prefer `-format tsv` for human review; to
populate `SMOKE_NES` automatically use the **awk + paste** recipe under **wire
list** (filters out wrapper banner lines). Skip step 0 if the user already
supplied a verified comma list.

### 1 — Build the binary (once or after code changes)

```bash
cd /home/joji/Go/comm-layer-server
make benchmark_client
```

The wrapper auto-builds on first run, but a manual build surfaces compile
errors immediately.

### 2 — Check pod status

```bash
cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
bash k8s_run_test_client.sh --status --client comm-layer-server
```

Expected: pod `comm-layer-server-*` in `STATUS=Running`, `RESTARTS` low.

### 3 — Configure scale

```bash
# NEs from Get NE (step 0), or set manually.
export SMOKE_NES="9.168.96.118,9.168.96.101"

# Services per NE: -epipes N means N unique services created per NE in MDC.
export SMOKE_EPIPES=50          # 50 unique epipes per NE (smoke default)
# export SMOKE_EPIPES=200       # 200 per NE (mini-load)
# export SMOKE_EPIPES=1000      # 1 000 per NE (pre-target)

# Stable prefix — use the same value for create and cleanup.
export SMOKE_EPIPE_PREFIX="smoke"   # services: smoke0-epipe-1..smokeN-epipe-N

export SMOKE_CLIENT_PREFIX="smoke"
export SMOKE_READ_INTERVAL=0
```

### 4 — Run the smoke

```bash
cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
export WORKSPACE_ROOT=/home/joji/Go

bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -nes            "${SMOKE_NES}" \
  -epipes         "${SMOKE_EPIPES:-50}" \
  -epipe-prefix   "${SMOKE_EPIPE_PREFIX:-smoke}" \
  -client-prefix  "${SMOKE_CLIENT_PREFIX:-smoke}" \
  -read-interval  "${SMOKE_READ_INTERVAL:-0}"
```

After the run, **`-epipes` services per NE** (named `<prefix><neIdx>-epipe-1`
through `<prefix><neIdx>-epipe-<epipes>`) are visible in MDC.

The wrapper:

1. Kills any stale port-forward on `${CLS_FWD_PORT}`.
2. SSHes to `${K8S_NODE_IP}` and runs `kubectl port-forward
   svc/comm-layer-server 9001` on the jump host, exposed on
   `${CLS_FWD_PORT}` (default 40055).
3. Waits for the tunnel handshake (3 s pause built in).
4. Runs `bin/benchmark_client -server ${K8S_NODE_IP}:${CLS_FWD_PORT} …` with
   the flags above.

### 5 — Cleanup (after user confirms)

Remove exactly the services created in step 4 (same NEs, same count, same prefix):

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -nes            "${SMOKE_NES}" \
  -epipes         "${SMOKE_EPIPES:-50}" \
  -epipe-prefix   "${SMOKE_EPIPE_PREFIX:-smoke}" \
  -client-prefix  "${SMOKE_CLIENT_PREFIX:-smoke}" \
  -cleanup
```

> **Legacy cleanup** (one-time, for runs before the prefix scheme):
>
> ```bash
> bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
>   -nes "${SMOKE_NES}" -client-prefix smoke -cleanup-legacy
> ```

## Pass criteria

A successful run prints (per NE):

```text
[<neId>] all <submissions> submissions sent, waiting for notifications...
```

Then the **Results** block:

```text
=== Results ===

NE 9.168.96.118:
  Submitted: 50, Succeeded: 50, Failed: 0
  Ack latency: avg=…ms p50=…ms p95=…ms max=…ms (n=50)
  E2E latency: avg=…ms p50=…ms p95=…ms max=…ms (n=50)
  BulkSize est (cluster=100ms): min=… max=… avg=… batches=…

=== Aggregate ===
Total wall-clock time: <duration>
Total epipe entries in successful payloads (1 per write): <sum over NEs>
Throughput: <X.X> epipes/sec
Success rate: 100.0%
```

**Required:**

- `Submitted == epipes` (equals `-epipes` when every submit ACKs)
- `Succeeded == Submitted` per NE (no `Failed`)
- `Success rate: 100.0%` aggregate
- No `timeout waiting for notifications` line printed
- Wall clock within budget (see scaling table below)

Allowed warnings (do not fail the run):

- `read checkpoint after submission N` — informational only.
- `deploy stream recv error: Canceled` after all notifications received — benign
  (stream closes as the run completes).
- gRPC deadline propagation warnings in the pod log, as long as the deploy
  stream still reports `Succeeded`.

## Post-run summary (REQUIRED)

After every run the agent MUST produce a **per-NE table** (ALL NEs as rows —
never truncate with `…`) and an **aggregate row** regardless of mode. Both
must include the **BulkSize** report (min / max / avg).

### Parsing rules by mode

**epipe / srl mode** — parse `=== Results ===` block:
- Each NE block: `NE <neId>:\n  Submitted: N, Succeeded: N, Failed: N`
- Timing: `Ack latency: … p95=X max=X` and `E2E latency: … p95=X max=X`
- Aggregate: `=== Aggregate ===` → wall clock, throughput, success rate

**bulk SR mode** — parse per-NE single-line `done` entries and DONE line:
- Per NE: `  NE <neId>  ok=N  fail=N  elapsed=T  Ack(p95=Y)  E2E(avg=Z p95=W max=V)`
- Aggregate: `=== SR bulk-per-NE DONE … configs=N events OK/FAIL=N/N elapsed=T (R req/s) ===`
  followed by `    estimated bulkSize (cluster window=…):  min=X  max=Y  avg=Z  batches=N`

**bulk SRL mode** — parse `=== SRL bulk per-NE ===` block and DONE line:
- Per NE: `  NE <neId>  ok=N  fail=N  elapsed=T  Ack(p95=Y)  E2E(avg=Z p95=W max=V)`
- Aggregate: `=== SRL bulk DONE … iters=N configs=N OK/FAIL=N/N elapsed=T (R req/s) ===`
  followed by `    estimated bulkSize (cluster window=…):  min=X  max=Y  avg=Z  batches=N`

### Per-NE table (all modes) — ALL rows required, no truncation

| NE | OK | Fail | Elapsed | Ack p95 | E2E avg | Entries |
|----|----|------|---------|---------|---------|---------|
| 9.168.96.186 | 100 | 0 | 12.9 s | 3.64 s | 8.7 s | 2 000 |
| 9.168.96.173 | 100 | 0 | 13.7 s | 3.55 s | 10.2 s | 2 000 |
| *(one row per NE — never omit rows)* | | | | | | |
| **Total** | **2 000** | **0** | — | — | — | **40 000** |

**"OK"** = successful `AsyncUpdateHierarchyObjects` RPCs. **"Entries"** = actual
objects deployed:

- **bulk SR**: `OK × batchSize` epipe+iface pairs (e.g. 100 batches × 20 = 2 000 per NE).
- **bulk SRL**: `OK × 2` interface objects (e.g. 50 iters × 2 = 100 per NE).
- **epipe mode**: `OK` unique epipes (1 per RPC).

### Aggregate row (all modes)

| Wall clock | Configs | Throughput | BulkSize min / max / avg (clusters) | Success rate | Status |
|------------|---------|------------|--------------------------------------|--------------|--------|
| 15.8 s | 80 000 | 126.3 req/s | 4 / 108 / 38.5 (52) | 100.0 % | PASS |

- **Configs**: `configs=N` from the DONE line (total objects pushed to workers).
- **Throughput**: `R req/s` from the DONE line (RPC submissions per second).
- **BulkSize min/max/avg**: from `estimated bulkSize … min=X max=Y avg=Z batches=N`.
  Higher avg = better server-side coalescing. Higher max shows burst capacity.
  Always report all three values — omitting min/max hides variance.
- **Status**: PASS when `OK/FAIL=N/0`; FAIL when any NE has `fail > 0` or
  `E2E max` exceeds budget (e.g. `> 30 s` at smoke scale, `> 60 s` at full scale).

Mark `Status = FAIL` and highlight the failing NE row if `fail > 0` or `E2E max`
is above budget.

## Cross-check with server metrics (optional)

While the smoke is running or right after, scrape comm-layer-server metrics
(via Grafana — see `nsp-k8s-grafana` skill — or `kubectl port-forward
svc/comm-layer-server 9090`):

```promql
# admission rate
sum by (method) (rate(comm_layer_config_rpc_total{method=~"async_.*"}[1m]))

# deploy delivery outcome
sum by (result) (rate(comm_layer_notif_deploy_delivery_total[1m]))

# pending writes by reason (any non-zero is suspicious during a smoke)
sum by (reason) (rate(comm_layer_notif_deploy_delivery_total{result="pending"}[1m]))

# (after phase7b/7c) bulking effectiveness — avg units per dispatched batch
sum(rate(comm_layer_bulk_dispatched_units_total[1m]))
  / sum(rate(comm_layer_bulk_dispatched_batches_total[1m]))

# (after phase7b) fraction of dispatcher calls that were single-unit
sum(rate(comm_layer_bulk_dispatched_batches_total{kind="single"}[1m]))
  / sum(rate(comm_layer_bulk_dispatched_batches_total[1m]))
```

In a healthy smoke run all deliveries should appear under `result="sent"`;
`pending` / `send_failed` / `persist_failed` should be zero. Once phase 7b/7c
are in place, the average-units-per-batch ratio should grow above 1 under load.

## Scaling up toward the 80-NE / 4 K-epipe target

Once the 2-NE / 50-service smoke is green, scale in stages and check the same
pass criteria each time. **`-epipes N` = N unique services per NE in MDC.**

| Step | NEs | Services/NE (`-epipes`) | Total services | Time budget |
|------|-----|------------------------|----------------|-------------|
| Smoke | 2 | 50 | 100 | ≤ ~90 s |
| Mini-load | 4 | 200 | 800 | ≤ 2 min |
| Pre-target | 20 | 1 000 | 20 000 | ≤ 5 min |
| Full target | 80 | 4 000 | 320 000 | ≤ 20 min |

Watch for the failure modes called out in `docs/design/async_bulk_write_design.md`
under **Performance, Scaling, and Resource Controls**:

- Pod memory growth (slice head leak in `neQueue.items`)
- `bulk_limited_by` distribution skewed entirely to one cap (re-tune the other)
- `comm_layer_notif_deploy_delivery_total{result="pending", reason="backpressure"}`
  rising — `deployStreamBufferSize` too small or notification fan-out too slow.

## Troubleshooting

### `Unavailable: async admission not configured`

Pod was built without admission/bulk wiring or `configWriteBulkingEnabled=false`.
Check `kustomize/base/configmap.yaml` and pod logs for `"bulk drainer started"`.

### All submissions fail with `dial tcp ...: connection refused`

Port-forward died. Re-run from step 4. If repeated, the jump host port
`${CLS_FWD_PORT}` may be busy — set `CLS_FWD_PORT` to a free port in
`k8s_test_env.local`.

### NEs accept submissions but never receive notifications (timeout printed)

Either the deploy stream did not register (check pod log for
`"deployment stream registered"` with the smoke `clientId`), or the bulk
drainer is stuck. Inspect:

```bash
kubectl logs -n nsp-communicator -l app=comm-layer-server --tail=200 \
  | grep -E 'bulk drainer|deploy|ticket'
```

### `error reading server preface: EOF` on first RPC

Same as the gNMI smoke — kubectl tunnel not fully established. The wrapper
already waits 3 s after the TCP listener appears; if the error persists,
increase the `sleep` in `k8s_run_test_client.sh:start_port_forward`.

### Some NEs ok, others FAILURE in `AsyncDeployResponseInfo`

NE itself rejected the edit (existing service, bad name, NE down). Inspect
`AdditionalInfo` in the comm-layer-server log:

```bash
kubectl logs -n nsp-communicator -l app=comm-layer-server --tail=500 \
  | grep -E '<failingNeId>|errorMessages='
```
description: >-
  Run a reduced-scale async bulk write smoke test for comm-layer-server against
  the K8s cluster using cmd/benchmark_client (asyncUpdateHierarchyObjects +
  receiveEventDeploymentNotifications). Includes **Get NE**: query device-registry
  (`GetNeEntries` via test_client `-cmd get-ne-entries`) over the same
  k8s-test-client tunnel, with optional `-ne-type`, `-ne-version`, and
  `-protocol` filters, then wire IDs into `SMOKE_NES`. For epipe/srl smoke,
  `-nes` is **required** (no lab defaults in the binary). Async writes per NE
  (`-epipes`) and clientId prefix are configurable via env vars or flags.
  **Epipe mode** (default) uses `bulkbench.BuildSRBulkPayload` per
  `AsyncUpdateHierarchyObjects` (2–3 epipes + iface each; `-batch` ignored).
  **SRL smoke** (`-mode srl`) uses `bulkbench.BuildSRLBulkPayload` per write (two
  interfaces per RPC; same shape as `rpc_test_client` SRL bulk). **Bulk mode** (`-mode bulk`) drives SR1K + SRL payloads from
  `cmd/rpc_test_client/bulkbench` (same shapes as `rpc_test_client` bulk paths): configurable
  entries per SR NE, SRL iteration count, **remove** cleanup for SR, deploy
  tracking, inferred **bulk size** stats, and **consecutive-failure stop**.
  After the run the agent MUST produce a per-NE summary table (see "Post-run
  summary") for epipe smoke. Use when asked to smoke test comm-layer-server bulk
  write, discover NEs for a smoke, run SR/SRL scale loads, or run a small async
  bulk run against the cluster.
---

# Smoke Test — comm-layer-server Async Bulk Write

Runs `cmd/benchmark_client` against the **comm-layer-server** pod in K8s. The
client fires `AsyncUpdateHierarchyObjects` RPCs per NE in parallel, registers a
`ReceiveEventDeploymentNotifications` stream per `clientId`, and waits for the
terminal `AsyncDeployResponseInfo` per ticket. Pass/fail is determined by
per-ticket success and aggregate wall clock.

Reuses `k8s-test-client` (SSH + kubectl port-forward) — the wrapper now
recognizes the `comm-layer-benchmark` client which port-forwards
`pod:9001 -> jump:${CLS_FWD_PORT}` and runs `bin/benchmark_client -server …`.

## Default smoke scale (configurable)

| Parameter | Default (smoke) | Full target | Override |
|-----------|-----------------|-------------|----------|
| NEs | 2 | 80 | `SMOKE_NES` (comma list) or `-nes` |
| Async writes per NE (`-epipes`) | 50 | 4 000 | `SMOKE_EPIPES` or `-epipes` |
| `-batch` (epipe mode) | — (ignored) | — | `SMOKE_BATCH` still accepted; no effect on epipe payloads |
| Read checkpoint interval | 0 (off) | 50 | `SMOKE_READ_INTERVAL` or `-read-interval` |
| Client prefix | `smoke` | `benchmark` | `SMOKE_CLIENT_PREFIX` or `-client-prefix` |

At smoke defaults: 2 NEs × **50 async writes** each; each write is
`BuildSRBulkPayload(i,"create")` (**2 or 3** epipes + matching router interfaces,
alternating). Successful payloads sum to **~125 epipe entries per NE** (25×2 +
25×3) when all 50 submits succeed — **~250 epipe entries** aggregate. Expected
wall clock on a healthy cluster: **under ~90 s** (more RPCs than the old
bench-epipe batching).

> **NE selection:** Prefer **Get NE** (below) so `SMOKE_NES` matches what
> device-registry already routes. NE IDs are passed verbatim in the gRPC
> request. You may still use a fixed pair (e.g. the SRL set from
> `smoke-test-gnmi`) when you already know they are registered.

## Concurrency layout

Per NE goroutine in the benchmark client:

1. Opens a `ReceiveEventDeploymentNotifications` stream with
   `clientId = <prefix>-<neId>`.
2. Loops **`-epipes`** times, issuing `AsyncUpdateHierarchyObjects` each with
   `bulkbench.BuildSRBulkPayload(iter, "create")` (**`-mode epipe`**) or
   `bulkbench.BuildSRLBulkPayload(srlStartIter+iter)` (**`-mode srl`**), matching
   `rpc_test_client` bulk loops.
3. Counts notifications from the deploy stream; finishes when total
   `successes + failures == submissions` (dynamic wait budget from submission
   count).

Across NEs the loops run **in parallel** (one goroutine per NE).

## `benchmark_client` modes

| `-mode` | Meaning |
|---------|---------|
| `epipe` (default) | SR **bulkbench** smoke: each write `BuildSRBulkPayload(i,"create")`; `-nes`, `-epipes`, `-cleanup` (one `BuildSRBulkPayload(0,"delete")` per NE). `-batch` ignored. |
| `srl` | SRL **bulkbench** smoke: each write `BuildSRLBulkPayload(srlStartIter+i)` (two `ethernet-1/*` interfaces per RPC). **`-nes` is required** (comma SRL NE IDs); `-srl-start-iter` rotates pairs; `-cleanup` is a no-op. |
| `bulk` | **SR + SRL lab payloads** from `cmd/rpc_test_client/bulkbench` (shared with `rpc_test_client`): SR uses `ne1k-epipe-*` + router ifaces (service IDs from `SR1KBase`); SRL rotates `ethernet-1/1`…`1/32` interface pairs. SR **delete** uses `_action_: remove` on the same ID windows as create. |

### Bulk mode — main flags

| Flag | Role |
|------|------|
| `-sr-entries-per-ne N` | SR: `N` epipe+iface **per NE** (0 = skip SR). Align `N` with `-batch` (`N % batch == 0`). |
| `-srl-iters M` | SRL: `M` total `AsyncUpdateHierarchyObjects` calls, round-robin on `-srl-ne` (0 = skip SRL). |
| `-batch` | SR: objects per ticket (default 20). More tickets per NE → larger bulk merge opportunity (`-sr-parallel 0` fans out all). |
| `-sr-parallel` | SR: max concurrent batch RPCs **per NE** (0 = all batches at once for max bulking). |
| `-srl-parallel` | SRL: max in-flight submits (0 = all `srl-iters` at once). |
| `-sr-op` | SR operation: `create` or `delete` (same SR1K IDs); `remove` is an alias for `delete`. |
| `-sr-ne`, `-srl-ne` | Comma NE lists for **bulk** mode only; **required** when `-sr-entries-per-ne` or `-srl-iters` is non-zero (no baked-in lab IDs). Use **Get NE** to populate. |
| `-client-pool` | SRL: deploy-notification client pool size (default 5). |
| `-bulk-cluster-ms` | Window for **BulkSizeTracker** inference (default 100). |
| `-max-fail-streak` | After **N** consecutive submit/deploy failures, stop launching new RPCs (0 = off). |
| `-deadline-min` | Parent context for the whole bulk run (default 300). |
| `-deploy-wait-sr-min` / `-deploy-wait-srl-min` | Per-ticket wait caps (default 10 / 4 minutes). |
| `-srl-start-iter` | Seed for `BuildSRLBulkPayload` rotation (default 0). |

SR and SRL legs run **in parallel** when both counts are non-zero. Each leg
prints **estimated bulkSize** (min / max / avg / clusters) from notification
completion clustering, matching the idea behind `bulkSizeTracker` in
`cmd/rpc_test_client/internal/testclient/bulk_async.go` (now implemented in
`cmd/rpc_test_client/bulkbench/tracker.go`).

### Bulk mode — examples

Create **6000** epipe+iface entries per SR NE and **1000** SRL interface batches
(max fan-out on both legs):

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -mode bulk \
  -sr-entries-per-ne 6000 \
  -srl-iters 1000 \
  -batch 20 \
  -sr-parallel 0 \
  -srl-parallel 0 \
  -client-prefix smoke
```

**Delete SR** footprint created above (same ID layout per NE — use the same
`-batch` alignment as create):

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -mode bulk \
  -sr-entries-per-ne 6000 \
  -sr-op delete \
  -batch 20 \
  -sr-parallel 0 \
  -srl-iters 0 \
  -client-prefix smoke
```

**Custom NE pools** (e.g. after Get NE), still max bulking:

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -mode bulk \
  -sr-ne "9.168.96.101,9.168.96.118,9.168.96.158,9.168.96.186" \
  -srl-ne "92.4.201.116,92.3.202.71,92.2.197.18,92.1.203.111" \
  -sr-entries-per-ne 2000 \
  -srl-iters 200 \
  -batch 20 \
  -sr-parallel 0 \
  -max-fail-streak 10 \
  -client-prefix smoke
```

## Prerequisites

1. `k8s-test-client` env configured.
2. `source /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client/k8s_test_env.sh`
3. `export WORKSPACE_ROOT=/home/joji/Go`
4. `comm-layer-server` deployed in `nsp-communicator` with **bulking enabled**
   (`configwrite.bulking.enabled=true`). Confirm with `--status` below.
5. (Optional) **device-registry** reachable for Get NE — same jump host;
   confirm with `bash k8s_run_test_client.sh --status --client device-registry`.

## Get NE (device-registry)

**Purpose:** Before scaling or when the user asks for cluster NEs, call
**device-registry** `RegistryService.GetNeEntries` in non-interactive mode
(`runNonInteractive` in `device-registry/cmd/test_client.go`) so the bulk smoke
targets NEs the registry actually knows.

**Transport:** Same `k8s-test-client` env as the benchmark: SSH to
`${K8S_NODE_IP}`, `kubectl port-forward` **device-registry** on
`jump:${DR_FWD_PORT}` (default **40058**) → pod gRPC. Set
`export WORKSPACE_ROOT=/home/joji/Go` so `k8s_run_test_client.sh` resolves the
`device-registry` repo.

### Get NE — flags and optional env

| Filter / output | CLI flag | Example | Notes |
|-----------------|----------|---------|-------|
| NE type | `-ne-type` | `-ne-type SR-7750` | Exact match per registry (e.g. `7250-IXR-SRL`, `7730-SXR-SRL`) |
| NE version | `-ne-version` | `-ne-version 24.10.R4` | Combine with `-ne-type` to narrow further |
| Protocol | `-protocol` | `-protocol gnmi` or `-protocol netconf` | Values: `gnmi` \| `netconf` (omit for all) |
| Output | `-format` | `text` (default), `ids`, `tsv`, `json` | **`tsv`** for scripted `SMOKE_NES` (see wire recipe); `ids` is fine for copy-paste |

Optional convenience (shell only; not read by `test_client`):

```bash
export SMOKE_NE_TYPE=""        # e.g. SR-7750
export SMOKE_NE_VERSION=""     # e.g. 24.10.R4
export SMOKE_NE_PROTOCOL=""    # gnmi or netconf
```

### Get NE — run (workspace script)

```bash
cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
export WORKSPACE_ROOT=/home/joji/Go

# All NEs, machine-readable (TSV header + rows)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries \
  -format tsv

# Refined list: SRL family only (example)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries -ne-type 7250-IXR-SRL -format tsv

# gNMI-capable NEs only (example)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries -protocol gnmi -format tsv

# Combine filters (example)
bash k8s_run_test_client.sh --client device-registry -- \
  -cmd get-ne-entries -ne-type SR-7750 -ne-version 24.10.R4 -format ids
```

### Get NE — shortcut from device-registry repo

```bash
cd /home/joji/Go/device-registry
export WORKSPACE_ROOT=/home/joji/Go
./bin/k8s_dr_test.sh -- \
  -cmd get-ne-entries -ne-type SR-7750 -format tsv
```

(`bin/k8s_dr_test.sh` sources the same `k8s_test_env.sh` and invokes
`k8s_run_test_client.sh --client device-registry`.)

### Get NE — wire list into `SMOKE_NES`

`k8s_run_test_client.sh` prints status lines to stdout before the binary runs, so
**do not** pipe raw `-format ids` straight into `paste` without filtering. Prefer
**`-format tsv`** and keep only real data rows (four tab-separated columns; skip
the `ne_id` header):

```bash
export SMOKE_NES="$(
  cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
  source k8s_test_env.sh
  export WORKSPACE_ROOT=/home/joji/Go
  bash k8s_run_test_client.sh --client device-registry -- \
    -cmd get-ne-entries \
    ${SMOKE_NE_TYPE:+-ne-type "$SMOKE_NE_TYPE"} \
    ${SMOKE_NE_VERSION:+-ne-version "$SMOKE_NE_VERSION"} \
    ${SMOKE_NE_PROTOCOL:+-protocol "$SMOKE_NE_PROTOCOL"} \
    -format tsv 2>&1 | awk -F'\t' 'NF==4 && $1!="ne_id" {print $1}' | paste -sd, -
)"
```

For a **fixed smoke pair** (two SRL NEs), you can still set `SMOKE_NES` by hand
once Get NE confirms those IDs exist.

### Get NE — agent behavior

When the user asks to **get NEs first**, **discover NEs**, or **filter by type /
protocol** before a bulk smoke: run Get NE (at least once with `-format tsv` or
`ids`), present the table or ID list, then set `SMOKE_NES` (or a subset) for
steps 3–4.

### Get NE — SSH / known_hosts

If SSH fails with `Host key verification failed` or `known_hosts` permission
errors from the agent environment, retry with e.g.
`K8S_SSH_OPTS="-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/tmp/k8s_dr_known_hosts"`
for that invocation, or add the same to `k8s_test_env.local`.

## Agent steps

### 0 — Get NE list (when NEs are unknown or filters are requested)

Run **Get NE** (section above). Prefer `-format tsv` for human review; to
populate `SMOKE_NES` automatically use the **awk + paste** recipe under **wire
list** (filters out wrapper banner lines). Skip step 0 if the user already
supplied a verified comma list.

### 1 — Build the binary (once or after code changes)

```bash
cd /home/joji/Go/comm-layer-server
make benchmark_client
```

The wrapper auto-builds on first run, but a manual build surfaces compile
errors immediately.

### 2 — Check pod status

```bash
cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
bash k8s_run_test_client.sh --status --client comm-layer-server
```

Expected: pod `comm-layer-server-*` in `STATUS=Running`, `RESTARTS` low.

### 3 — Configure scale (optional — defaults are smoke-safe)

```bash
# Override defaults; leave unset to use the defaults table above.
# Prefer SMOKE_NES from Get NE (step 0); fallback example for two SRL NEs:
export SMOKE_NES="92.4.201.116,92.3.202.71"
export SMOKE_EPIPES=50                          # AsyncUpdateHierarchyObjects per NE
export SMOKE_BATCH=4                            # ignored in epipe mode; used for -mode bulk
export SMOKE_CLIENT_PREFIX="smoke"
export SMOKE_READ_INTERVAL=0
```

### 4 — Run the smoke

```bash
cd /home/joji/Go/agentic-workspace/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
export WORKSPACE_ROOT=/home/joji/Go

bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -nes            "${SMOKE_NES:-92.4.201.116,92.3.202.71}" \
  -epipes         "${SMOKE_EPIPES:-50}" \
  -batch          "${SMOKE_BATCH:-4}" \
  -client-prefix  "${SMOKE_CLIENT_PREFIX:-smoke}" \
  -read-interval  "${SMOKE_READ_INTERVAL:-0}"
```

The wrapper:

1. Kills any stale port-forward on `${CLS_FWD_PORT}`.
2. SSHes to `${K8S_NODE_IP}` and runs `kubectl port-forward
   svc/comm-layer-server 9001` on the jump host, exposed on
   `${CLS_FWD_PORT}` (default 40055).
3. Waits for the tunnel handshake (3 s pause built in).
4. Runs `bin/benchmark_client -server ${K8S_NODE_IP}:${CLS_FWD_PORT} …` with
   the flags above.

### 5 — Cleanup (separate run)

After a smoke that creates services, remove them so the next run starts clean:

```bash
bash k8s_run_test_client.sh --client comm-layer-benchmark -- \
  -nes "${SMOKE_NES:-92.4.201.116,92.3.202.71}" \
  -epipes "${SMOKE_EPIPES:-50}" \
  -client-prefix "${SMOKE_CLIENT_PREFIX:-smoke}" \
  -cleanup
```

## Pass criteria

A successful run prints (per NE):

```text
[<neId>] all <submissions> submissions sent, waiting for notifications...
```

Then the **Results** block:

```text
=== Results ===

NE 92.4.201.116:
  Submitted: 13, Succeeded: 13, Failed: 0
  Ack latency  count=13 avg=…ms p50=…ms p95=…ms max=…ms
  E2E latency  count=13 avg=…s  p50=…s  p95=…s  max=…s

=== Aggregate ===
Total wall-clock time: <duration>
Total epipe entries in successful payloads (2|3 per write): <sum over NEs>
Throughput: <X.X> epipe entries/sec
Success rate: 100.0%
```

**Required:**

- `Submitted == epipes` (async writes per NE; equals `-epipes` when every submit ACKs)
- `Succeeded == Submitted` per NE (no `Failed`)
- `Success rate: 100.0%` aggregate
- No `timeout waiting for notifications` line printed
- Wall clock within budget. At smoke defaults (~50 writes × 2 NEs, bulkbench
  payloads):
  - Healthy: **≤ ~90 s**
  - Concerning: 90–180 s (worker / dispatcher slow path)
  - Fail: > 180 s or any NE timeouts

Allowed warnings (do not fail the run):

- `read checkpoint after submission N` — informational only.
- gRPC deadline propagation warnings in the pod log, as long as the deploy
  stream still reports `Succeeded`.

## Post-run summary (REQUIRED)

Same rules as the **Post-run summary** section above: per-NE table with ALL
NEs as rows (no truncation), aggregate row with BulkSize min/max/avg. For
epipe/srl mode parse from `=== Results ===`; for bulk modes parse per-NE
single-line `done` entries (`bulk SR`) or `=== SRL bulk per-NE ===` block
(`bulk SRL`) and the respective DONE lines for BulkSize.

## Cross-check with server metrics (optional)

While the smoke is running or right after, scrape comm-layer-server metrics
(via Grafana — see `nsp-k8s-grafana` skill — or `kubectl port-forward
svc/comm-layer-server 9090`):

```promql
# admission rate
sum by (method) (rate(comm_layer_config_rpc_total{method=~"async_.*"}[1m]))

# deploy delivery outcome
sum by (result) (rate(comm_layer_notif_deploy_delivery_total[1m]))

# pending writes by reason (any non-zero is suspicious during a smoke)
sum by (reason) (rate(comm_layer_notif_deploy_delivery_total{result="pending"}[1m]))

# (after phase7b/7c) bulking effectiveness — avg units per dispatched batch
sum(rate(comm_layer_bulk_dispatched_units_total[1m]))
  / sum(rate(comm_layer_bulk_dispatched_batches_total[1m]))

# (after phase7b) fraction of dispatcher calls that were single-unit
sum(rate(comm_layer_bulk_dispatched_batches_total{kind="single"}[1m]))
  / sum(rate(comm_layer_bulk_dispatched_batches_total[1m]))
```

In a healthy smoke run all deliveries should appear under `result="sent"`;
`pending` / `send_failed` / `persist_failed` should be zero. Once phase 7b/7c
are in place, the average-units-per-batch ratio should grow above 1 under load
(the smoke is too small to fully exercise bulking — see the scaling staircase
below).

## Scaling up toward the 80-NE / 4 K-epipe target

Once the 2-NE / 50-write smoke is green, scale in stages and check the same
pass criteria each time. **Epipe entries** ≈ `writes/NE × NEs × 2.5` (2 and 3
alternate per write).

| Step | NEs | Writes/NE | ~Epipe entries (payload sum) | Time budget |
|------|-----|-----------|-------------------------------|-------------|
| Smoke | 2 | 50 | ~250 | ≤ ~90 s |
| Mini-load | 4 | 200 | ~3 200 | ≤ 2 min |
| Pre-target | 20 | 1 000 | ~50 000 | ≤ 5 min |
| Full target | 80 | 4 000 | ~800 000 | ≤ 20 min |

Watch for the failure modes called out in `docs/design/async_bulk_write_design.md`
under **Performance, Scaling, and Resource Controls**:

- Pod memory growth (slice head leak in `neQueue.items`)
- `bulk_limited_by` distribution skewed entirely to one cap (re-tune the other)
- `comm_layer_notif_deploy_delivery_total{result="pending", reason="backpressure"}`
  rising — `deployStreamBufferSize` too small or notification fan-out too slow.

## Troubleshooting

### `Unavailable: async admission not configured`

Pod was built without admission/bulk wiring or `configWriteBulkingEnabled=false`.
Check `kustomize/base/configmap.yaml` and pod logs for `"bulk drainer started"`.

### All submissions fail with `dial tcp ...: connection refused`

Port-forward died. Re-run from step 4. If repeated, the jump host port
`${CLS_FWD_PORT}` may be busy — set `CLS_FWD_PORT` to a free port in
`k8s_test_env.local`.

### NEs accept submissions but never receive notifications (timeout printed)

Either the deploy stream did not register (check pod log for
`"deployment stream registered"` with the smoke `clientId`), or the bulk
drainer is stuck. Inspect:

```bash
kubectl logs -n nsp-communicator -l app=comm-layer-server --tail=200 \
  | grep -E 'bulk drainer|deploy|ticket'
```

### `error reading server preface: EOF` on first RPC

Same as the gNMI smoke — kubectl tunnel not fully established. The wrapper
already waits 3 s after the TCP listener appears; if the error persists,
increase the `sleep` in `k8s_run_test_client.sh:start_port_forward`.

### Some NEs ok, others FAILURE in `AsyncDeployResponseInfo`

NE itself rejected the edit (existing service, bad name, NE down). Inspect
`AdditionalInfo` in the comm-layer-server log:

```bash
kubectl logs -n nsp-communicator -l app=comm-layer-server --tail=500 \
  | grep -E '<failingNeId>|errorMessages='
```
