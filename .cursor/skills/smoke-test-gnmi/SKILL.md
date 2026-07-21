---
name: smoke-test-gnmi
description: >-
  Run the parallel read/write smoke test for comm-worker-gnmi against K8s-deployed
  SRL NEs. Fires 25 concurrent gRPC requests (reads + writes) across 4 NEs × 2
  rounds via kubectl port-forward. After the run the agent MUST produce a
  per-NE summary table (see "Post-run summary" section). Use when asked to smoke
  test gNMI, run the parallel test, verify concurrent R/W health on the cluster,
  or get a structured breakdown of reads per NE.
---

# Smoke Test — comm-worker-gnmi Parallel R/W

Runs **case 17** of `worker_test_client`: 25 concurrent gRPC requests (reads and
writes) spread across 4 SRL NEs, repeated for **2 rounds** (50 RPCs total).
Uses the `k8s-test-client` infrastructure (SSH tunnel + kubectl port-forward).

## NE matrix

The test client hard-codes the following NEs in
`comm-worker-gnmi-go/cmd/worker_test_client/main.go`:

| Label | NE ID          | Mgmt IP           | Port  | Policy   | Model                |
|-------|----------------|-------------------|-------|----------|----------------------|
| NE-A  | 92.4.201.116   | 100.127.201.116   | 57400 | SRL_GNMI | 7250-IXR-SRL 25.10.1 |
| NE-B  | 92.3.202.71    | 100.127.202.71    | 57400 | SRL_GNMI | 7250-IXR-SRL 25.10.1 |
| NE-C  | 92.2.197.18    | 100.127.197.18    | 57400 | SRL_GNMI | 7730-SXR-SRL 25.7.1  |
| NE-D  | 92.1.203.111   | 100.127.203.111   | 57400 | SRL_GNMI | 7730-SXR-SRL 24.10.1 |

> **Important**: requests sent directly to the mediation worker must carry a
> `ConnectionInfo` with `MediationPolicyId` (e.g. `SRL_GNMI`) and the target NE's
> management IP:port. The session key is derived as `<policy>@<mgmtIP>:<port>`,
> for example `SRL_GNMI@100.127.203.111:57400`. The test client's `neConn.connInfo()`
> method builds this automatically.

## Concurrency layout (case 17) — 25 requests × 2 rounds

| NE   | Total | Reads (immediate / queued*)                                           | Write |
|------|-------|-----------------------------------------------------------------------|-------|
| NE-A | 5     | interfaces, net-instance / system*, routing-policy*                   | set   |
| NE-B | 7     | interfaces, tunnel / acl*, system*, net-instance*, routing-policy*    | set   |
| NE-C | 6     | interfaces, acl / fan-tray*, system*, net-instance*                   | set   |
| NE-D | 7     | interfaces, acl / fan-tray*, system*, net-instance*, routing-policy*  | set   |

MaxReadsPerSession=2: the first two reads per NE run immediately; all others
queue (marked `*`) and drain as slots open. Writes use an independent slot.
Case 17 fires both rounds sequentially — 25 goroutines released simultaneously
each round, 50 RPCs total.

## Prerequisites

1. `k8s-test-client` skill env is configured (see that skill's SKILL.md).
2. `source workspace-settings/.cursor/scripts/k8s-test-client/k8s_test_env.sh`
3. `export WORKSPACE_ROOT=/home/joji/Go`

## Agent steps

### 1 — Build the binary (once, or after code changes)

```bash
cd /home/joji/Go/comm-worker-gnmi-go
make test_client
```

### 2 — Check pod status

```bash
cd /home/joji/Go/workspace-settings/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
bash k8s_run_test_client.sh --status --client comm-worker-gnmi
```

Expected: pod `comm-worker-gnmi-*` in `STATUS=Running`, `RESTARTS` low.

### 3 — Run the parallel smoke test

Preferred (uses the wrapper with the `sleep 1` tunnel-ready fix):

```bash
cd /home/joji/Go/workspace-settings/.cursor/scripts/k8s-test-client
source k8s_test_env.sh
export WORKSPACE_ROOT=/home/joji/Go
printf '17\n19\n' | bash k8s_run_test_client.sh --client comm-worker-gnmi 2>&1
```

Manual variant (if the wrapper is not available):

```bash
ssh -o ConnectTimeout=5 -o BatchMode=yes root@$K8S_NODE_IP \
  "fuser -k ${GNMI_FWD_PORT}/tcp 2>/dev/null; true; \
   kubectl port-forward -n nsp-communicator pod/<pod-name> \
     --address 0.0.0.0 ${GNMI_FWD_PORT}:50051" &
PF_PID=$!
for i in $(seq 1 20); do sleep 0.5; nc -z -w1 $K8S_NODE_IP $GNMI_FWD_PORT && break; done
sleep 1   # let kubectl tunnel handshake complete — avoids "server preface EOF"
printf '17\n19\n' | \
  /home/joji/Go/comm-worker-gnmi-go/bin/worker_test_client \
    -addr $K8S_NODE_IP:$GNMI_FWD_PORT 2>&1
kill $PF_PID 2>/dev/null; wait $PF_PID 2>/dev/null; true
```

Capture the full stdout. The log is also saved automatically to
`comm-worker-gnmi-go/bin/worker_test_client_output.log`.

### 4 — Interpret results

A successful run prints two rounds. Each round looks like:

```
=== Round N — Launching 25 concurrent requests across 4 SRL NEs ===
  NE-A (92.4.201.116): 4R+1W  — interfaces, net-instance, system, routing-policy
  ...

Task (* = queued)         Kind   Elapsed       Result
------------------------------------------------------------------------
NE-C write-1              write  143ms         ok
NE-B read-2 tunn          read   164ms         5 items
...
NE-A read-1 iface         read   612ms         39 items

Round N: all 25 done in 612ms (wall clock)
```

**Pass criteria:**
- All 25 rows per round show `Result` = `N items` (reads) or `ok` (writes). No `ERR:` lines.
- Wall clock typically 500ms – 1.5s per round for a healthy cluster. Round 2 is
  often faster because gRPC connections and gNMI sessions are already warm.

### 5 — Post-run summary (REQUIRED after every successful run)

After capturing the output the agent MUST produce a summary table for each
round. Parse each output line using the following rules:

- A line is a task row if it matches: `NE-X <task-name>  <kind>  <elapsed>  <result>`
- `kind` is `read` or `write`.
- A read is **immediate** if the task name contains no `*`; **queued** if it does.
- `result` for reads is `N items`; extract N.
- `result` for writes is `ok` (or an error string).

Produce one table per round in this format:

| NE   | Imm. reads | Queued reads | Total reads | Items read | Writes | Write result | Wall clock |
|------|-----------|--------------|-------------|------------|--------|--------------|------------|
| NE-A | 2         | 2            | 4           | 43         | 1      | ok           | —          |
| NE-B | 2         | 4            | 6           | 55         | 1      | ok           | —          |
| NE-C | 2         | 3            | 5           | 43         | 1      | ok           | —          |
| NE-D | 2         | 4            | 6           | 56         | 1      | ok           | —          |
| **Total** | **8** | **13**    | **21**      | **197**    | **4**  | **all ok**   | **612ms**  |

Then produce a two-row cross-round comparison:

| Round | Total reads | Total items | Writes ok | Wall clock | Status  |
|-------|-------------|-------------|-----------|------------|---------|
| 1     | 21          | 197         | 4/4       | 612ms      | PASS    |
| 2     | 21          | 197         | 4/4       | 519ms      | PASS    |

Fill in `FAIL` and highlight the offending NE/task if any row shows `ERR:`.

## Troubleshooting

### "error reading server preface: EOF" on all requests
Port-forward TCP listener was open but the tunnel to the pod was not yet
established. Fix: add `sleep 1` after the `nc -z` loop (already applied to
`k8s_run_test_client.sh`). If running manually, ensure the manual sleep is present.

### All ERRs, pod log shows nothing from your run
The port-forward was not up at all. Verify `kubectl port-forward` started on
the jump host and the forward port is not blocked by a firewall or in use.

### "connection error: desc = transport: Error while dialing"
Port-forward on the jump host was killed or died. Re-run from step 3.

### Some NEs fail, others succeed
The failing NEs may have lost their gNMI session (NE reboot, path change).
Check the pod logs:
```bash
kubectl logs -n nsp-communicator <pod> --tail=50 | grep <neId>
```

### Write fails but reads succeed
The write target (subinterface index) may already exist or have been deleted in
a prior run. Cases 12/13 in the test client manage the subinterface lifecycle;
run case 13 (BatchSet delete) first if the set operation returns AlreadyExists.
