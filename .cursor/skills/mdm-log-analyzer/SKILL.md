---
name: mdm-log-analyzer
description: >-
  Collects and analyzes Nokia MDM (mediation) logs from Kubernetes pods or customer SCP/SFTP
  servers, parses MdmServer.log and rolled zip archives, detects issues across adapter install,
  resync, bulk upload, stuck NEs, thread pools (mdm-grpc-exec, sshd-SshClient), memory
  (MemoryMonitorPrintTimer), ZooKeeper (connection-event-worker), GC and thread dumps.
  Produces markdown reports and HTML dashboards with charts. Use when the user asks to analyze
  MDM logs, troubleshoot mdm-server pods, resync failures, bulk upload, NE stuck, memory/GC,
  or cluster log correlation.
---

# MDM Log Analyzer

## When to apply

Use this skill for MDM operational troubleshooting: log collection, parsing, correlation, recommendations, and reports. Prefer **Cursor Canvas** or the generated **HTML dashboard** when the user asks for charts, timelines, or graphical analysis.

## Mandatory execution order (default: cluster via jump host)

When running this skill against the **configured cluster** (see [`mdm-log-analyzer.env`](mdm-log-analyzer.env)), follow these steps **in order**. SSH keys are assumed **already loaded** (non-interactive `ssh` is OK unless the user says otherwise).

1. **Load configuration** — Read [`mdm-log-analyzer.env`](mdm-log-analyzer.env) (same directory as this file), or the file in **`MDM_LOG_ANALYZER_ENV`**. Note **`MDM_K8S_NODE_IP`** (canonical jump/node host), **`MDM_NAMESPACE`**, **`MDM_MDM_SERVER_POD`**, **`MDM_LOG_ROOT`**, and optional **`MDM_KUBECONFIG`** / **`MDM_K8S_CONTEXT`**.

2. **SSH to the access host** — Connect to the host that can reach the Kubernetes API (usually **`MDM_K8S_NODE_IP`**, or **`MDM_LOCAL_SERVER_IP`** if set). **Skip this step** if `kubectl` from the analyst machine already reaches the cluster with **`MDM_KUBECONFIG`** / **`MDM_K8S_CONTEXT`**.
   - `ssh -o BatchMode=yes "${MDM_LOCAL_SSH_USER:-root}@${MDM_LOCAL_SERVER_IP:-$MDM_K8S_NODE_IP}"`  
   Use **`BatchMode=no`** only if a password is required. From that session (or from the user’s machine if `kubectl` already targets the cluster), continue.

3. **`kubectl` to MDM pod(s)** — List/verify pods, then target **`mdm-server-*`** in **`MDM_NAMESPACE`**:
   - `kubectl get pods -n "$MDM_NAMESPACE" -l '...'` or `grep mdm-server` as appropriate; use **`MDM_K8S_CONTEXT`** / **`MDM_KUBECONFIG`** from env when set.
   - For HA, repeat **step 4** for each **`mdm-server-0` … `mdm-server-(N-1)`** after listing pods in step 3 (see **`MDM_CLUSTER_POD_COUNT`** in env if documented).

4. **Collect log data** — Copy mediation logs from each pod (**`MDM_LOG_ROOT`**, typically `/opt/nsp/mediation/log` including `MdmServer.log` and date subdirs / `*.log.zip`). Use `collect_logs.sh k8s` or equivalent `kubectl cp -c cn-nsp-mdm-server`.

4b. **Collect live diagnostics** — Run immediately after log collection (same session), using `collect_logs.sh diag` or the commands below. Output files land alongside the log snapshot for joint analysis. Use `-i` (no `-t`) for piped capture; use `-it` only in an interactive terminal.

   | Diagnostic | Command | Output |
   |-----------|---------|--------|
   | Thread dump | `kubectl exec -i -n $NS $POD -c $CTR -- app-console threads > $OUT/threads-<ts>.txt` | stdout → file |
   | NE list | `kubectl exec -i -n $NS $POD -c $CTR -- app-console ne-list > $OUT/ne-list-<ts>.txt` | stdout → file |
   | All queues (summary) | `kubectl exec -i -n $NS $POD -c $CTR -- app-console queues > $OUT/queues-<ts>.txt` | stdout → file |
   | Queue detail dump | `kubectl exec -i -n $NS $POD -c $CTR -- app-console "queue-dump mdm-grpc-exec /tmp/mdm-grpc-exec.txt"` then `kubectl cp $NS/$POD:/tmp/mdm-grpc-exec.txt $OUT/queue-dump-mdm-grpc-exec-<ts>.txt -c $CTR` | file inside pod → copy out |

   Where `$NS=$MDM_NAMESPACE`, `$POD=$MDM_MDM_SERVER_POD`, `$CTR=$MDM_MDM_SERVER_CONTAINER` (`cn-nsp-mdm-server`).  
   Default queue for detail dump: **`mdm-grpc-exec`** (`MDM_DIAG_QUEUE`). Pass `--all-queues` to `collect_logs.sh diag` to dump every queue found in `queues` output.

5. **Upload scripts to jump host** — `scp -r scripts/ root@${MDM_K8S_NODE_IP}:/tmp/mdm-scripts/`. The jump host has **Python 3.9.25** (confirmed 2026-04-30); no Python is required on the analyst machine.

6. **Run the pipeline on the jump host** — SSH in and execute:
   ```bash
   python3 /tmp/mdm-scripts/scripts/run_pipeline.py <JUMP_HOST_LOG_DIR> \
     --out-dir /tmp/mdm-analysis-<ts> \
     [--gc <JUMP_HOST_LOG_DIR>/GC_logs/<gc-file>.log]
   ```
   GC log is at `MDM_GC_LOG_PATH` inside the collected dir (e.g. `GC_logs/GC_trace_*.log`).

7. **Retrieve results and open report** — SCP the three output files to a timestamped local dir (`C:\NSP\MDM\mdm-analysis-<ts>\`), then **always** print the exact Chrome URL and open it:
   ```powershell
   $ts = "<ts>"   # same timestamp used for collection
   $localDir = "C:\NSP\MDM\mdm-analysis-$ts"
   $sshKey   = "$env:USERPROFILE\.ssh\id_ed25519"
   New-Item -ItemType Directory -Path $localDir -Force | Out-Null
   scp -i $sshKey "root@100.127.194.35:/tmp/mdm-analysis-$ts/report.md"    "$localDir\report.md"
   scp -i $sshKey "root@100.127.194.35:/tmp/mdm-analysis-$ts/report.html"  "$localDir\report.html"
   scp -i $sshKey "root@100.127.194.35:/tmp/mdm-analysis-$ts/findings.json" "$localDir\findings.json"

   $url = "file:///" + $localDir.Replace("\","/") + "/report.html"
   Write-Host "Report: $url"
   Start-Process "chrome.exe" $url
   ```
   > **ALWAYS print `$url` in the chat** so the user can click the correct report. Never reference the skill sample (`skills/mdm-log-analyzer/out/report/report.html`).

> **ALWAYS run steps 5–7 on the jump host (`MDM_K8S_NODE_IP`)**. Never attempt to run `run_pipeline.py` on the analyst Windows machine — Python is not installed there.

If the user **only** has logs on disk already, skip steps 2–4 and upload scripts + run pipeline directly on whichever host holds the logs.

## Environment file (server + download location)

1. Copy [mdm-log-analyzer.env.example](mdm-log-analyzer.env.example) to `mdm-log-analyzer.env` in the same folder (the real file is gitignored).
2. For **Kubernetes**, set **`MDM_NAMESPACE`**, **`MDM_MDM_SERVER_POD`**, and optionally **`MDM_K8S_CONTEXT`** / **`MDM_KUBECONFIG`**. For **logs already on disk**, set **`MDM_LOGS_LOCAL_DIR`** (and optionally **`MDM_MDM_LOCAL=true`** so analysis uses that path first).
3. For **customer SCP**, set **`MDM_CUSTOMER_LOG_SERVER`**, **`MDM_SCP_USER`**, **`MDM_CUSTOMER_REMOTE_LOG_PATH`**, and **`MDM_CUSTOMER_LOGS_DOWNLOAD_DIR`**.
4. For **SSH to a local MDM host** (`root@IP` typical), set **`MDM_K8S_NODE_IP`** to the same server; **`MDM_LOCAL_SERVER_IP`** only if SSH must differ. Run **`./scripts/collect_logs.sh ssh`**. Use an **interactive terminal** for password prompts if keys are not used.
5. **`collect_logs.sh`** auto-sources `mdm-log-analyzer.env` next to `SKILL.md`, or the path in **`MDM_LOG_ANALYZER_ENV`**.
6. For analysis, use the download/snapshot directory as `parse_mdm_logs.py` input. Optionally set **`MDM_ANALYSIS_WORK_DIR`** for `parsed.json` / `findings.json` / reports.

| Variable | Purpose |
|----------|---------|
| `MDM_KUBECONFIG` | Path to kubeconfig file for `kubectl` |
| `MDM_K8S_CONTEXT` | `kubectl --context` name (select cluster) |
| `MDM_K8S_NODE_IP` | Canonical node/jump host IP — **same host** used for SSH (`collect_logs.sh ssh`) when **`MDM_LOCAL_SERVER_IP`** is unset |
| `MDM_CLUSTER_POD_COUNT` | Optional: StatefulSet replica count (`mdm-server-0` … `N-1`) |
| `MDM_HA_ACTIVE_STANDBY` | Optional: HA split hint, e.g. `2+1` (3 pods), `4+1` or `3+2` (5 pods), `5+2` (7 pods) |
| `MDM_LOCAL_SERVER_IP` | Optional SSH-only host; if unset, **`MDM_K8S_NODE_IP`** is used (same server as K8s MDM) |
| `MDM_NAMESPACE` | K8s namespace (default `nsp-psa-privileged`) |
| `MDM_MDM_SERVER_POD` | Default pod for `kubectl cp` (e.g. `mdm-server-0`) |
| `MDM_LOG_ROOT` | Path inside pod (default `/opt/nsp/mediation/log`) |
| `MDM_LOGS_LOCAL_DIR` | Local folder that already contains `MdmServer.log` / zip trees (no `kubectl`) |
| `MDM_MDM_LOCAL` | If `true`, prefer **`MDM_LOGS_LOCAL_DIR`** for analysis when collecting is skipped |
| `MDM_LOCAL_SSH_USER` | SSH user for **`ssh`** mode (default **`root`**) |
| `MDM_LOCAL_REMOTE_LOG_PATH` | Remote log directory (default same as **`MDM_LOG_ROOT`**) |
| `MDM_LOCAL_SSH_PORT` | SSH port (falls back to **`MDM_SCP_PORT`**, then 22) |
| `MDM_LOCAL_LOGS_DOWNLOAD_DIR` | Local base for **`ssh`** pulls (`mdm-ssh-<timestamp>` subdirs) |
| `MDM_CUSTOMER_LOG_SERVER` | Customer log host (IP or DNS) for **`scp`** mode |
| `MDM_SCP_USER` | SSH user for **`scp`** (customer) |
| `MDM_SCP_PORT` | Optional SSH port (non-22) |
| `MDM_CUSTOMER_REMOTE_LOG_PATH` | Remote log root (often `/opt/nsp/mediation/log`) |
| `MDM_CUSTOMER_LOGS_DOWNLOAD_DIR` | Local base for customer SCP downloads (`mdm-scp-<timestamp>` subdirs) |
| `MDM_K8S_LOGS_DOWNLOAD_DIR` | Local base for `kubectl cp` / `local` snapshot output (`mdm-k8s-*` / `mdm-local-*`) |
| `MDM_LOG_ANALYZER_ENV` | Override path to the env file |
| `MDM_ANALYSIS_WORK_DIR` | Suggested place for parsed JSON, findings, and HTML report |
| `MDM_MDM_SERVER_CONTAINER` | Container for `kubectl exec`/`cp` (default `cn-nsp-mdm-server`, not the fluent-bit sidecar) |
| `MDM_DIAG_QUEUE` | Queue name for `queue-dump` in `collect_logs.sh diag` (default `mdm-grpc-exec`) |
| `MDM_DIAG_ALL_QUEUES` | If `true`, dump all queues listed by `app-console queues` automatically |

## Prerequisites (ask every run)

Defaults saved in [`mdm-log-analyzer.env`](mdm-log-analyzer.env) (updated 2026-04-30) — use without prompting unless the user overrides:

| Preference | Saved default |
|------------|---------------|
| **Log source** (`MDM_DEFAULT_LOG_SOURCE`) | `k8s` — SSH to node `MDM_K8S_NODE_IP`, then `kubectl cp` from mdm-server pods |
| **Retention** (`MDM_LOG_RETENTION_DAYS`) | `10` — active `MdmServer.log` + full 10-day rolled zip retention |
| **GC logs** (`MDM_INCLUDE_GC_LOGS`) | `true` — pass `--gc` to `run_pipeline.py` / `parse_mdm_logs.py` |
| **Analysis scope** (`MDM_ANALYSIS_SCOPE`) | `all` — all domains: adapter, resync, bulk upload, stuck NEs, threads, memory/GC, ZooKeeper |

1. **Log source:** Default = Kubernetes (`k8s`). SSH to `MDM_K8S_NODE_IP`, validate pod list, then `kubectl cp` per pod. Override with `ssh`, `scp`, or `local` only when specified.
2. **Cluster/node access:** Use `MDM_K8S_NODE_IP` from env unless user provides a different context/kubeconfig.
3. **Customer SCP/SFTP:** Use `mdm-log-analyzer.env` customer variables; ask only if they are missing.
4. **Date range:** Default = current `MdmServer.log` + all available rolled zips (up to `MDM_LOG_RETENTION_DAYS=10`).

## MDM log layout (on pod / server)

| Item | Path / pattern |
|------|------------------|
| Namespace | `nsp-psa-privileged` (default from user) |
| Pods | `mdm-server-0`, `mdm-server-1`, ... |
| Live log | `/opt/nsp/mediation/log/MdmServer.log` |
| Rolled logs | `/opt/nsp/mediation/log/YYYY-MM-DD/MdmServer.YYYY-MM-DD.N.log.zip` |
| Retention | ~10 days |

MDM is commonly a **StatefulSet** with `mdm-server-0` … `mdm-server-(N-1)`. In **HA** deployments some pods are **active** and others **standby** (for example 3 replicas: 2 active + 1 standby; 5: 4+1 or 3+2; 7: 5+2). Document **`MDM_CLUSTER_POD_COUNT`** and **`MDM_HA_ACTIVE_STANDBY`** in env; collect **`kubectl cp` per pod** (or iterate pods) when you need a full cluster picture.

Example exec: `kubectl exec -it -n nsp-psa-privileged mdm-server-0 -- bash`

Copy out: `kubectl cp nsp-psa-privileged/mdm-server-0:/opt/nsp/mediation/log ./mdm-logs-mdm-server-0/`

## Workflow (4 phases)

For the **default cluster path**, the steps above (**SSH → kubectl → collect → upload scripts → run pipeline on jump host → retrieve results**) are required. The sections below break this into **collect → parse → analyze → report** detail.

> **All Python steps (parse / analyze / report) run on the jump host (`MDM_K8S_NODE_IP`)**. The analyst machine (Windows) does not have Python. Scripts are uploaded once per session with `scp -r scripts/ root@${MDM_K8S_NODE_IP}:/tmp/mdm-scripts/`.

### 1. Collect

- SSH to jump host: `ssh -i ~/.ssh/id_ed25519 root@${MDM_K8S_NODE_IP}`
- `kubectl cp ${MDM_NAMESPACE}/${MDM_MDM_SERVER_POD}:${MDM_LOG_ROOT} /tmp/mdm-logs-k8s-<ts>/ -c ${MDM_MDM_SERVER_CONTAINER}`
  - Use **`MDM_MDM_SERVER_CONTAINER`** (`cn-nsp-mdm-server`) — **not** the fluent-bit sidecar (`nsp-mdm-server-log`).
  - GC logs land in `<collected_dir>/GC_logs/` (path: **`MDM_GC_LOG_PATH`**).
- For HA: repeat `kubectl cp` for each pod (`mdm-server-0` … `mdm-server-(N-1)`).
- Then `scp -r root@${MDM_K8S_NODE_IP}:/tmp/mdm-logs-k8s-<ts>/ <local-dir>/` to keep a local archive copy.

### 1b. Collect live diagnostics (run after 1, same output dir)

Run **`./scripts/collect_logs.sh diag [--pod POD] [--out DIR] [--all-queues]`** (or the equivalent commands individually). All outputs land in the same `<ts>` snapshot directory as the logs for joint parsing.

```bash
NS=nsp-psa-privileged
POD=mdm-server-0                          # or MDM_MDM_SERVER_POD from env
CTR=cn-nsp-mdm-server                     # MDM_MDM_SERVER_CONTAINER
OUT=/tmp/mdm-logs-k8s-<ts>
TS=$(date +%Y%m%d-%H%M%S)

# 1) Thread dump — active JVM threads + stack traces
kubectl exec -i -n $NS $POD -c $CTR -- app-console threads \
  > $OUT/threads-${TS}.txt
echo "Threads saved: $OUT/threads-${TS}.txt"

# 2) NE list — registered NEs with state/version
kubectl exec -i -n $NS $POD -c $CTR -- app-console ne-list \
  > $OUT/ne-list-${TS}.txt
echo "NE list saved: $OUT/ne-list-${TS}.txt"

# 3) All queue summary — queue names, sizes, active threads
kubectl exec -i -n $NS $POD -c $CTR -- app-console queues \
  > $OUT/queues-${TS}.txt
echo "Queue summary saved: $OUT/queues-${TS}.txt"

# 4) Queue detail dump for mdm-grpc-exec (file written inside pod, then copied out)
#    Use MDM_DIAG_QUEUE to override the queue name.
QUEUE=${MDM_DIAG_QUEUE:-mdm-grpc-exec}
POD_TMP="/tmp/${QUEUE}-dump.txt"
kubectl exec -i -n $NS $POD -c $CTR -- app-console "queue-dump ${QUEUE} ${POD_TMP}"
kubectl cp $NS/$POD:${POD_TMP} $OUT/queue-dump-${QUEUE}-${TS}.txt -c $CTR
echo "Queue dump saved: $OUT/queue-dump-${QUEUE}-${TS}.txt"
```

**Notes:**
- Use `-it` instead of `-i` only when running from an **interactive terminal** (not for piped/scripted capture).
- `app-console queues` gives names for all active queues — use that output to decide which to `queue-dump` in detail.
- Pass `--all-queues` to `collect_logs.sh diag` to automatically dump every queue listed in `queues` output.
- **Repeat for each HA pod** to compare thread/queue state across active/standby members.
- These files are picked up automatically by `run_pipeline.py` when present in the log dir (pass `--threaddump threads-*.txt` explicitly if not auto-detected).

### 2. Parse (on jump host)

- Upload scripts once: `scp -r scripts/ root@${MDM_K8S_NODE_IP}:/tmp/mdm-scripts/`
- SSH to jump host and run:
  ```bash
  python3 /tmp/mdm-scripts/scripts/parse_mdm_logs.py /tmp/mdm-logs-k8s-<ts>/ \
    -o /tmp/mdm-analysis-<ts>/parsed.json \
    --gc /tmp/mdm-logs-k8s-<ts>/GC_logs/GC_trace_*.log
  ```
- Parser accepts plain `.log`, `.log.zip`, and walks nested date directories.

### 3. Analyze (on jump host)

- ```bash
  python3 /tmp/mdm-scripts/scripts/analyze_logs.py /tmp/mdm-analysis-<ts>/parsed.json \
    -o /tmp/mdm-analysis-<ts>/findings.json
  ```
- Ask **follow-up questions** when findings are ambiguous (maintenance window, NE count, recent config change).
- Compare **thread dumps** (if provided) to log lines in the same time window; see [analysis-patterns.md](analysis-patterns.md).

### 4. Report (on jump host, retrieve locally)

- ```bash
  python3 /tmp/mdm-scripts/scripts/generate_report.py /tmp/mdm-analysis-<ts>/findings.json \
    -o /tmp/mdm-analysis-<ts>/report.md \
    --html /tmp/mdm-analysis-<ts>/report.html
  ```
- **Or use the single-step shortcut** (preferred):
  ```bash
  python3 /tmp/mdm-scripts/scripts/run_pipeline.py /tmp/mdm-logs-k8s-<ts>/ \
    --out-dir /tmp/mdm-analysis-<ts>/ \
    --gc /tmp/mdm-logs-k8s-<ts>/GC_logs/GC_trace_*.log \
    --threaddump /tmp/mdm-logs-k8s-<ts>/threads-*.txt
  ```
  If diagnostics were collected, also pass `--threaddump` so thread dumps are correlated with log timestamps.
- Retrieve to analyst machine and open in Chrome:
  ```powershell
  $ts      = "<ts>"
  $localDir = "C:\NSP\MDM\mdm-analysis-$ts"
  $sshKey  = "$env:USERPROFILE\.ssh\id_ed25519"
  $node    = "100.127.194.35"   # MDM_K8S_NODE_IP
  New-Item -ItemType Directory -Path $localDir -Force | Out-Null
  scp -i $sshKey "root@${node}:/tmp/mdm-analysis-$ts/report.md"     "$localDir\report.md"
  scp -i $sshKey "root@${node}:/tmp/mdm-analysis-$ts/report.html"   "$localDir\report.html"
  scp -i $sshKey "root@${node}:/tmp/mdm-analysis-$ts/findings.json" "$localDir\findings.json"

  $url = "file:///" + $localDir.Replace("\","/") + "/report.html"
  Write-Host "Report: $url"
  Start-Process "chrome.exe" $url
  ```
  > **ALWAYS print the `$url` value in the chat after retrieval** so the user can click the correct report directly. Never point to the skill sample at `skills/mdm-log-analyzer/out/report/report.html`.
- Optionally mirror key charts in **Canvas** for interactive review.

## Hound (code cross-reference)

Base: `http://orbw-web.ca.alcatel-lucent.com:6080/`

Query URL pattern:

`?q=<SEARCH_TERM>&i=nope&literal=nope&files=&excludeFiles=&repos=`

Replace `<SEARCH_TERM>` with class names, `full-resync`, `GrpcExecutor`, etc. Include links in findings and the markdown report.

## Growing the skill

When a **new recurring scenario** is confirmed:

1. Add a pattern block to [analysis-patterns.md](analysis-patterns.md) using the template at the top.
2. Optionally extend `analyze_domain_*` functions in [scripts/analyze_logs.py](scripts/analyze_logs.py).

## Key threads and subsystems

| Thread / name | Role |
|---------------|------|
| `mdm-grpc-exec` | gRPC client/server work (pool size from config, often `mdm.core.grpc.exec-pool.size`) |
| `sshd-SshClient` | SSH/NETCONF/CLI (MINA SSHD) |
| `MemoryMonitorPrintTimer` | Periodic JVM memory logging |
| `connection-event-worker-*` | ZooKeeper client events |

## Reference docs

- [analysis-patterns.md](analysis-patterns.md) — searchable patterns and Hound hints
- [gc-analysis-guide.md](gc-analysis-guide.md) — GC log interpretation
- [report-template.md](report-template.md) — report outline

## Scripts (quick reference)

| Script | Purpose |
|--------|---------|
| `scripts/collect_logs.sh` | `k8s`, `scp`, `ssh`, `local`, or **`diag`** (threads / ne-list / queues / queue-dump) |
| `scripts/parse_mdm_logs.py` | Structured JSON from logs + zips |
| `scripts/analyze_logs.py` | Domain analyses → findings JSON |
| `scripts/generate_report.py` | `report.md` + `report.html` from `findings.json` |
| `scripts/run_pipeline.py` | One command: parse → analyze → report (writes under **`out/report/`** by default) |

## Python

> **Python runs on the jump host only.** The analyst Windows machine has no Python installation. Always SSH to `root@MDM_K8S_NODE_IP` and invoke `python3` there.

- Jump host Python: **3.9.25** (confirmed 2026-04-30 on `MDM_K8S_NODE_IP=100.127.194.35`)
- Requires Python 3.8+. No extra pip packages required for core scripts (stdlib only).
- Scripts live at `/tmp/mdm-scripts/scripts/` after `scp -r scripts/ root@${MDM_K8S_NODE_IP}:/tmp/mdm-scripts/`

**Single-step report on jump host:**

```bash
python3 /tmp/mdm-scripts/scripts/run_pipeline.py <log_dir> \
  [--out-dir DIR] [--gc PATH ...] [--threaddump PATH ...]
```
