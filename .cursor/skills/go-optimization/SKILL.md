---
name: go-optimization
description: >-
  Evidence-first Go performance workflow: static anti-pattern sweep, escape
  analysis, pprof (CPU/heap/allocs/goroutine/mutex/block), benchmarks with
  benchstat, and severity-classified optimization reports. Prefers errgroup and
  semaphore over custom goroutine pools. Use when optimizing Go, reducing
  allocations, GC pressure, heap usage, adding pprof, running benchmarks, or
  reviewing resource usage in internal/ packages.
disable-model-invocation: true
---

# Go optimization

Measure before tuning. Do not raise timeouts or add caches without data.

Align timeout/latency investigations with the workspace **perf-rca** skill.
For wall-clock SVG flamegraphs, use **go-flamegraph** after pprof is wired.

## When to invoke

- User asks to optimize Go code, reduce allocations, or improve CPU/memory/FD usage.
- Reviewing hot paths (gRPC handlers, merge/registry loops, dispatchers).
- Adding or interpreting `pprof`, escape analysis, or `go test -bench`.
- Suspected goroutine leaks, unbounded maps, or custom worker pools.

## Context minimization (mandatory)

1. **Do not read whole repositories.** Start with the package named in the request.
2. **Static grep first** — targeted `Grep` for anti-patterns (see index below); open only matching files.
3. **Escape analysis** — run `scripts/escape_check.sh` on `./internal/PKG/...`; read only files in the top escape lines.
4. **pprof** — use `scripts/pprof_snapshot.sh` or `go tool pprof -top`; read only symbols that point at project `file:line`.
5. **Load reference docs on demand** — open `references/*.md` only for the step you are on.
6. **Ask before** enabling pprof on production-facing ports or widening profile endpoints beyond ops policy.

## Workflow

Copy and track:

```
Progress:
- [ ] 1. Scope package(s) and falsifiable hypothesis
- [ ] 2. Static anti-pattern sweep (grep)
- [ ] 3. Escape analysis (escape_check.sh)
- [ ] 4. Runtime profiles (if service runnable) OR micro-benchmarks
- [ ] 5. Change smallest fix; benchstat A/B
- [ ] 6. go test -race ./PKG/...
- [ ] 7. Report (findings template); update plan.md for repo run
```

### 1. Hypothesis

State what resource is high (CPU, alloc rate, heap retained, goroutines, mutex wait)
and which function/package you expect. Example: "Subscribe merge allocates per path
in `merge.go` due to `fmt.Sprintf` in loop."

### 2. Static sweep

Run greps in the target tree only:

| Signal | Pattern / check |
|--------|-----------------|
| Proto logging cost | `Msgf\("%\+v"` , `Msgf\("%v",.*req` |
| Format in loop | `fmt.Sprintf` inside `for` |
| JSON reflection | `json.Marshal` on fixed-schema hot paths |
| Timer alloc | `time.After` in loops |
| Unsized growth | `make\(\[\]` / `make\(map` without capacity when `len(input)` known |
| Worker pools | `chan.*work`, fixed `N` goroutines + `select` for I/O fan-out |
| sync.Map | R/W-balanced maps — often wrong tool |

See workspace **go-code-rules.mdc** §4a table for logging/string/JSON/map rules.

### 3. Escape analysis

From repo root (or skill scripts dir):

```bash
workspace-settings/.cursor/skills/go-optimization/scripts/escape_check.sh ./internal/TARGET/...
```

Details: [references/escape-analysis.md](references/escape-analysis.md)

### 4. Runtime profiling

Wire `net/http/pprof` behind config (see [references/pprof-profiling.md](references/pprof-profiling.md)).

```bash
export PPROF_URL=http://127.0.0.1:8080
scripts/pprof_snapshot.sh
```

Interpret **flat** (self time/allocs) vs **cum** (inclusive). CPU for compute;
`allocs` / heap for GC pressure; `goroutine` for leaks; `mutex` / `block` for contention.

### 5. Benchmarks

Add table-driven `Benchmark*` next to the hot function. Baseline before change:

```bash
scripts/bench_delta.sh -pkg ./internal/PKG -bench BenchmarkName -count 10
```

Details: [references/benchmarking.md](references/benchmarking.md)

**Gate:** `benchstat` must not show significant regression on ns/op and B/op unless
documented trade-off. Run `go test -race` on touched packages.

### 6. Report

Use [references/findings-report-template.md](references/findings-report-template.md).
Number findings `O-NN`. Store repo report under `docs/actual/optimization-report.md`
unless the user specifies another path.

Track run metadata in [plan.md](plan.md) (do not edit the Cursor plan file in
`~/.cursor/plans/`).

## Idiomatic safety rails

**Prefer:**

- `golang.org/x/sync/errgroup` with `context.Context` for parallel I/O with first-error cancel.
- `golang.org/x/sync/semaphore.Weighted` to cap concurrency (NE/session limits).

**Avoid:**

- Custom goroutine pools (`chan work` + `select`) for I/O-bound RPC/etcd/Kafka — goroutines are cheap; pool complexity often adds latency and bugs.

**sync.Map:** only when keys are written once and read often, or goroutines own disjoint keys.
Otherwise `sync.RWMutex` + `map`.

**sync.Pool / manual JSON / string builders:** only after `benchmem` or alloc profile proves benefit.

Worked examples: [references/idiomatic-safety-rails.md](references/idiomatic-safety-rails.md)

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/escape_check.sh` | Rank escape-to-heap sites per package |
| `scripts/bench_delta.sh` | benchstat compare HEAD vs `BASE_REF` |
| `scripts/pprof_snapshot.sh` | Download standard pprof profiles + `-top` |
| `scripts/alloc_hotspots.py` | Tabulate alloc_objects from pprof text |

Run from target Go repo root; pass package paths as arguments to `escape_check.sh`.

## CI / build

In `.go-make` repos, after code changes run **build-go-repo** skill (`make build`, tests, delta if needed).

## Additional resources

- [pprof-profiling.md](references/pprof-profiling.md)
- [escape-analysis.md](references/escape-analysis.md)
- [benchmarking.md](references/benchmarking.md)
- [idiomatic-safety-rails.md](references/idiomatic-safety-rails.md)
- [findings-report-template.md](references/findings-report-template.md)
- [plan.md](plan.md) — skill and per-repo run tracker
