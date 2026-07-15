# MDM Log Analysis Patterns (Extensible Knowledge Base)

Append new entries when a scenario is confirmed. Each entry uses this template:

```markdown
### PATTERN-ID: Short name
- **Regex / search:** `...`
- **Thread (if any):** ...
- **Severity:** info|low|medium|high|critical
- **Interpretation:** ...
- **Recommended action:** ...
- **Hound search:** `term` → link with `?q=<term>&i=nope&literal=nope&files=&excludeFiles=&repos=`
```

**Hound base:** `http://orbw-web.ca.alcatel-lucent.com:6080/`

---

## Log layout (reference)

- Live: `/opt/nsp/mediation/log/MdmServer.log`
- Rolled: `/opt/nsp/mediation/log/YYYY-MM-DD/MdmServer.YYYY-MM-DD.N.log.zip` (about 10 days retained)
- Cluster member often visible as `mdm-server-N` in messages or pod name.

---

## Domain: Adapter installation

| Pattern | Regex / keywords | Thread | Severity | Notes |
|---------|------------------|--------|----------|-------|
| Adapter executor | `AdapterTaskExecutor`, `IRequestAdapter`, `IAdaptation` | Karaf / framework | medium | Lifecycle and regulation |
| Bundle failure | `BundleException`, `Unable to start`, `ServiceUnavailable` | various | high | Installation failure |
| OSGi / Karaf | `karaf`, `bundle`, `Blueprint` | various | medium | Correlate with adapter readiness |

**Hound:** `AdapterTaskExecutor`, `IRequestAdapter`

---

## Domain: Resync (full / partial)

| Pattern | Regex / keywords | Severity | Notes |
|---------|------------------|----------|-------|
| State machine | `fullResyncStarted`, `fullResyncDone`, `NodeResyncState`, `full-resync`, `fullResync` | varies | Pair start/done per NE |
| Failure | `resync.*fail`, `ResyncException`, `fullResync.*error` | high | Count per time window |
| NE correlation | NE id / hostname in same line as resync keywords | medium | Stuck NE detection |

**Hound:** `full-resync`, `NodeResyncState`, `RegisteredNe`, `DefaultFullResyncConverter`

---

## Domain: Bulk upload

| Pattern | Regex / keywords | Severity | Notes |
|---------|------------------|----------|-------|
| API | `IBulkUpload`, `BulkUpload`, `performBulkUpload`, `TriggerBulkUpload` | info | Start vs complete |
| Ratio | Count lines implying start vs complete/fail | medium | Imbalance = stuck jobs |

**Hound:** `IBulkUpload`, `IBulkUploadManager`, `TriggerBulkUpload`

---

## Domain: Stuck NEs

| Pattern | Regex / keywords | Severity | Notes |
|---------|------------------|----------|-------|
| Incomplete resync | NE with `fullResyncStarted` (or equivalent) without matching `fullResyncDone` within threshold | high | Tune threshold per SLA |
| Connection churn | Repeated connect/disconnect for same NE | medium | May pair with SSH/NETCONF |

---

## Domain: Thread pools

| Thread prefix | Role | Notes |
|---------------|------|-------|
| `mdm-grpc-exec` | gRPC execution pool (`GrpcExecutor`, `mdm.core.grpc.exec-pool.size`) | Watch saturation / queueing in messages |
| `sshd-SshClient` | Apache MINA SSHD (NETCONF ~90%, CLI ~10%) | Many threads = many sessions |
| `grpc-default-executor` | gRPC housekeeping | Less common in older stacks |

**Hound:** `GrpcExecutor`, `mdm-grpc-exec`

---

## Domain: Memory

| Pattern | Regex / keywords | Thread | Severity |
|---------|------------------|--------|----------|
| Memory monitor | `MemoryMonitor`, `MemoryMonitorPrintTimer`, heap, `free memory` | `MemoryMonitorPrintTimer` | medium |
| OOM | `OutOfMemoryError`, `Java heap space` | any | critical |

---

## Domain: ZooKeeper

| Pattern | Regex / keywords | Thread | Severity |
|---------|------------------|--------|----------|
| ZK client threads | `connection-event-worker` | `connection-event-worker-*` | medium |
| Session | `Session expired`, `Connection loss`, `KeeperException` | various | high |

---

## Domain: GC / JVM diagnostics

See [gc-analysis-guide.md](gc-analysis-guide.md). Keywords: `GC`, `Pause`, `Full GC`, `Metaspace`, `OutOfMemoryError`.

---

## Domain: Thread dumps

| Pattern | Notes |
|---------|-------|
| `"thread-name" #123` | Java thread dump header |
| `java.lang.Thread.State` | RUNNABLE, BLOCKED, WAITING — correlate blocked chains with `mdm-grpc-exec` / `sshd-SshClient` |
| `Found one Java-level deadlock` | critical — cite in report |

Compare dump timestamp window with `MdmServer.log` for the same period.
