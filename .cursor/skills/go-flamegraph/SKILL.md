---
name: go-flamegraph
description: >-
  Adds an interactive SVG flamegraph profiling endpoint to any Go HTTP service.
  Use when the user asks to add flamegraph, CPU profiling, wall-clock profiling,
  pprof flamegraph, or goroutine sampling to a Go project. Generates
  GET /debug/pprof/flamegraph with click-to-zoom, hover tooltips (time + %),
  memory stats header, and analysis badges. No external dependencies — stdlib only.
disable-model-invocation: true
---

# Go Flamegraph Profiling

Adds `GET /debug/pprof/flamegraph?seconds=N` to any Go HTTP service.

Collects wall-clock goroutine stack samples for N seconds via `runtime.Stack`
and returns a self-contained interactive SVG:
- Click-to-zoom (frame fills canvas width, subtree scales)
- Hover tooltip: full name · sample count · wall-clock time · % of total
- Memory stats header: heap alloc, delta, in-use, stack, GC count
- Analysis badges: Plateau (green) · Heavy path (amber) · System overhead (purple)

**No new dependencies** — stdlib only (`runtime`, `bytes`, `fmt`, `hash/fnv`,
`net/http`, `sort`, `strconv`, `strings`, `time`).

---

## Steps

### 1. Copy the implementation file

The complete, self-contained implementation lives at:

```
/home/joji/Go/comm-layer-server/internal/profiler/flamegraph.go
```

Read that file in full, then write it to the target project's profiling package
(e.g. `internal/profiler/flamegraph.go`). No edits needed except:

- **Package name** — change `package profiler` to match the target package.
- **Logger type** — the file uses `*zerolog.Logger`. If the target project uses a
  different logger, replace the two `s.logger.*` calls in `flamegraphHandler`
  with the project's equivalent.

### 2. Register the handler

In the HTTP server's `Start()` (or equivalent startup), add **before**
`http.ListenAndServe`:

```go
// Required: "GET " prefix avoids mux conflict with net/http/pprof's
// method-scoped patterns (Go 1.22+ enhanced mux).
http.HandleFunc("GET /debug/pprof/flamegraph", s.flamegraphHandler)
```

Also ensure the standard pprof side-effect import is present somewhere in the
package (gives /debug/pprof/ index, /profile, /heap, etc.):

```go
import _ "net/http/pprof"
```

**Critical:** omitting `GET ` causes a startup panic:
```
pattern "/debug/pprof/flamegraph" conflicts with pattern "GET /debug/pprof/"
```

### 3. Confirm no new dependencies

```bash
go mod tidy
```

No new entries should appear in `go.mod` or `go.sum`.

### 4. Build and verify

```bash
go build ./...
```

Run the service and confirm the startup log line:
```
INF pprof profiling server started addr=:6060
```

---

## Using the endpoint

```bash
# Collect 10-second flamegraph (blocks for the duration)
curl -o flamegraph.svg "http://localhost:6060/debug/pprof/flamegraph?seconds=10"

# Open in browser — WSL2
explorer.exe flamegraph.svg

# Or serve via HTTP (needed for full JS interactivity)
python3 -m http.server 8090
# → navigate to http://localhost:8090/flamegraph.svg
```

Query parameter: `seconds` — collection window, clamped to [1, 300], default 30.

---

## SVG features reference

| Feature | Detail |
|---------|--------|
| Hover tooltip | Name (truncated at 58 chars) · N samples · wall-clock time · % of total |
| Tag line | Appears on tooltip when frame is tagged: System overhead / Plateau / Heavy path |
| Click-to-zoom | Subtree fills full canvas width; siblings and ancestors hidden |
| Reset zoom | Button appears top-left; restores original layout |
| Memory header | `Heap alloc: X (+delta) · In-use: X · Stack: X · GC×N during window` |
| Legend | Footer bar explains badge colors |

## Analysis tag thresholds (tunable constants)

| Constant | Default | Meaning |
|----------|---------|---------|
| `plateauMinPct` | 2.0 | Self-time ≥ 2 % → Plateau badge |
| `heavyMinPct` | 8.0 | Total time ≥ 8 % with children → Heavy badge |
| `sampleIntervalMs` | 20 | Sampling interval in ms (50 Hz) |
| `defaultFlamegraphSeconds` | 30 | Default `?seconds` value |
| `maxFlamegraphSeconds` | 300 | Maximum `?seconds` value |

## Sampling semantics

`runtime.Stack(all=true)` captures **all goroutine states** — running, blocked
on gRPC/etcd/channel/mutex. This is wall-clock profiling, not CPU-only. For
network-heavy services this is intentional: I/O wait bottlenecks appear in the
flamegraph where CPU-only profiling would show nothing.

For pure CPU profiling, use the standard `net/http/pprof` endpoint:
```bash
go tool pprof -http=:8081 http://localhost:6060/debug/pprof/profile?seconds=30
```
