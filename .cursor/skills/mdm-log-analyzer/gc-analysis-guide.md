# GC Log Analysis (MDM / Java)

Use this guide when GC logs are present alongside `MdmServer.log` or in customer bundles.

## Locating GC Logs

- Often separate files: `gc.log`, `gc*.log`, or JVM output captured by the platform.
- JVM flags (examples): `-Xlog:gc*:file=gc.log:time,uptime,level,tags`, `-XX:+PrintGCDetails` (legacy).
- If only application logs mention GC, infer from `MemoryMonitorPrintTimer` and OOM lines.

## Parsing GC Lines (Modern `-Xlog:gc`)

Typical fragments:

- `Pause Young` / `Pause Full` — pause type
- `GC(123)` — GC number
- `Metaspace` — class metadata pressure
- `humongous` — G1 humongous objects (possible allocation issues)

Extract:

- **Pause duration** (ms) — compare to thresholds below.
- **Heap before/after** — trend of live set growth.
- **GC cause** — `Metadata GC Threshold`, `Allocation Failure`, `G1 Evacuation Pause`, etc.

## Histogram / Heap Dump References

- If logs reference **histogram** or **heap dump** paths, note path and time; correlate with thread dumps and MDM events (resync spikes, bulk upload).

## Warning Thresholds (Tuning Guidelines)

| Signal | Suggested threshold | Action |
|--------|---------------------|--------|
| Full GC frequency | > 1 per minute sustained | Review heap sizing, leak suspects, metaspace |
| Individual pause | > 500 ms (interactive SLA-sensitive) | Tune collector, reduce allocation spikes |
| Heap after GC | > 90% of max repeatedly | Increase heap or fix retention |
| Metaspace growth | Continuous growth without plateau | Classloader leak investigation |
| Humongous allocations | Frequent in G1 | Large object / buffer sizing in mediation |

## Correlation with MDM Logs

- Cross-check GC spikes with **bulk upload**, **full resync** bursts, **NETCONF** traffic (`sshd-SshClient`).
- OOM or `OutOfMemoryError` in `MdmServer.log` — prioritize heap + GC section in the report.

## Output for Reports

- Summarize: **worst pause**, **full GC count per window**, **heap trend** (if parseable).
- Link Hound searches for suspected allocators (e.g. large buffers in gRPC or netconf paths) using terms from stack traces if present.
