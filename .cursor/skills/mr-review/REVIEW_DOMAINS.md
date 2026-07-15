# MR Review — Per-Domain Checklists

Extended checklists referenced from [SKILL.md](SKILL.md).

---

## Design / Plan document

### Scope and completeness
- [ ] Are all deliverables listed in the Deliverables table?
- [ ] Do referenced files (linked docs, implementation tasks, tool sources) exist in
      the MR or in the repo?
- [ ] Is a follow-up ticket reference present if implementation is deferred?

### Schema / model loading (NSP-specific)
- [ ] Are all 5 ingest paths covered: `CreateSchema`, `UploadSchema` sequential,
      `UploadSchema` concurrent, `ReloadSchema`, URL-based via SDK?
- [ ] Is `ReloadSchema` tested during live query traffic? Is the delete-then-add
      window measured?
- [ ] Are all supported vendors in the fixture matrix: Nokia SRL, Nokia SR OS,
      Cisco IOS-XR, Juniper?
- [ ] Is N-3 release support modeled (4 simultaneous major releases loaded)?

### Performance dimensions
- [ ] Root path: `GetSchema(path="/", with_full_details=true)` tested?
- [ ] `ExpandPath(path="/")` response size and p99 defined?
- [ ] Cross-schema concurrent access (clients targeting different schemas) tested?
- [ ] Thundering herd at startup: K concurrent consumers calling simultaneously?
- [ ] Schema loading at runtime during active query traffic (mixed workload)?

### HA / DR
- [ ] Pod restart under load scenario present?
- [ ] Client reconnect time measured (dial timeout + retry latency)?
- [ ] Warm restart from persistent store measured separately from cold start?
- [ ] Readiness probe timing aligned to Kubernetes `initialDelaySeconds`?
- [ ] Multi-replica consistency test (if horizontal scale is claimed)?

### Pass/fail criteria
- [ ] SLOs defined for ALL tested RPCs, not just primary ones?
- [ ] Streaming RPCs have first-byte latency threshold?
- [ ] `ListSchemaMetadata` no-filter response size compared to `MaxCallRecvMsgSize`?
- [ ] Filter modes (no-filter, specific-schema, specific-schema+modules) are separate
      test matrix rows with own thresholds?

### CI portability
- [ ] Fixture paths use environment variables, not hardcoded developer paths?
- [ ] A fixture acquisition script or `make download-fixtures` target is defined?
- [ ] SDK/tool dependencies use tagged releases or `go.work` is documented?
- [ ] A `perf-compare` or `benchstat` regression tool is identified and in deliverables?

---

## Implementation (Go)

### Correctness
- [ ] No TODOs or commented-out code left in production paths?
- [ ] All error paths return or log — no silently swallowed errors?
- [ ] `ctx.Err()` checked in any loop that can run for >1 ms?

### Concurrency
- [ ] Is expensive work (YANG parse, proto serialize) done **outside** the critical
      lock section?
- [ ] Is `RLock` scope minimal — released before any blocking call?
- [ ] Are per-schema locks preferred over a single global lock when schemas are
      independent?
- [ ] Is a long `RLock` hold blocking writers via RWMutex starvation prevention?
      (Go blocks new readers once a writer is waiting.)

### gRPC
- [ ] New RPCs instrumented with Prometheus histogram interceptor?
- [ ] Retriable codes handled: `codes.Unavailable`, `codes.DeadlineExceeded`,
      `codes.ResourceExhausted`?
- [ ] `MaxCallRecvMsgSize` / `MaxCallSendMsgSize` set for any new streaming RPC?

### Tests
- [ ] Unit tests cover the new code path?
- [ ] Integration tests updated if RPC contract changed?
- [ ] Table-driven tests used where multiple input variants exist?

---

## Test / Benchmark

### Benchmark correctness
- [ ] `b.ResetTimer()` called after setup and before the measured loop?
- [ ] `b.StopTimer()` called before teardown?
- [ ] `b.ReportMetric` used for domain-specific units (MB/s, events/sec)?
- [ ] `-count=3` or higher used to reduce variance?

### Resource tracking
- [ ] `runtime.ReadMemStats` captured before AND after?
- [ ] `runtime.NumGoroutine` delta checked for leaks?
- [ ] pprof endpoint available during benchmark for offline analysis?

### Portability
- [ ] Server address / fixture paths driven by env vars or test flags?
- [ ] Build tags (`-tags load`, `-tags soak`) documented in README?
- [ ] `go.work` or module replace documented if test imports a sibling module?

---

## Deployment / Config

- [ ] New config keys added to `kustomize/base/configmap.yaml`?
- [ ] Default values are safe (not open, not zero-throttle)?
- [ ] Startup / liveness / readiness probe paths unchanged or updated?
- [ ] Container resource requests/limits updated to reflect new memory/CPU profile?
