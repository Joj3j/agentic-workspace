# MDM Log Analysis Report

## Environment

- **Cluster / customer ID:** [cluster name / customer ID]
- **Analysis date:** [YYYY-MM-DD HH:mm]
- **Servers analyzed:** mdm-server-0, mdm-server-1, ...
- **Log sources:** [K8s kubectl cp | SCP from IP:path | local directory]

---

## Executive Summary

[One paragraph: top 3 findings and overall health.]

---

## Critical Issues (Immediate Action)

| Severity | Area | Summary | Evidence |
|----------|------|---------|----------|
| Critical | | | |
| High | | | |

---

## Area Analysis

### Adapter Installation

- **Observations:** [timing, failures, bundle lifecycle]
- **Evidence:** [log excerpts with file/line context]
- **Hound:** [search links]

### Resync Performance

- **Frequency / timing / failures:** [metrics]
- **Stuck or incomplete resyncs:** [NE IDs if detected]
- **Hound:** [full-resync, NodeResyncState, etc.]

### Bulk Upload Health

- **Start/stop ratio, frequency:** [metrics]
- **Hound:** [IBulkUpload, TriggerBulkUpload]

### Stuck NEs

- **Candidates:** [NE IDs with started-but-not-done or repeated errors]
- **Threshold used:** [e.g. 24h without fullResyncDone]

### Thread Pool Utilization

- **mdm-grpc-exec:** [observations]
- **sshd-SshClient:** [observations]
- **Correlation with thread dumps:** [if available]

### Memory & GC

- **MemoryMonitorPrintTimer trends:** [summary]
- **GC pauses / heap:** [from GC logs if present]
- **Resource constraints:** [recommendations]

### ZooKeeper Connectivity

- **connection-event-worker activity:** [session loss, reconnects]
- **Evidence:** [excerpts]

---

## Hound Code References

Base URL: `http://orbw-web.ca.alcatel-lucent.com:6080/`

| Topic | Search term | Link |
|-------|-------------|------|
| Example | full-resync | `?q=full-resync&i=nope&literal=nope&files=&excludeFiles=&repos=` |

---

## Graphical Analysis

- **Dashboard:** [path or reference to generated `report.html`]
- **Charts:** timeline, thread pools, memory, GC histogram, resync ratio

---

## Recommendations

1. [Prioritized action]
2. [Prioritized action]
3. [Prioritized action]

---

## Appendix

- **Follow-up questions asked:** [list]
- **Patterns added to knowledge base:** [if any]
