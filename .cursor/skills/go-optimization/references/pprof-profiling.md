# Runtime profiling (pprof)

## Wire stdlib pprof (gated)

On the probe or admin HTTP mux only — not on untrusted interfaces without auth.

```go
import _ "net/http/pprof" // registers /debug/pprof/* on DefaultServeMux — prefer explicit mount

func mountPprof(r *mux.Router) {
    r.PathPrefix("/debug/pprof/").Handler(http.DefaultServeMux)
}
```

Or register on a dedicated `http.ServeMux` and attach to the app router.

**Go 1.22+:** if using `http.HandleFunc` patterns, avoid mux conflicts; see **go-flamegraph** skill (`GET /debug/pprof/flamegraph` vs `GET /debug/pprof/`).

Gate with env or config, e.g. `PPROF_ENABLED=true`. Default off in production ConfigMaps unless ops approves.

## Capture profiles

| Endpoint | Use |
|----------|-----|
| `/debug/pprof/profile?seconds=30` | CPU |
| `/debug/pprof/heap` | In-use heap |
| `/debug/pprof/allocs` | Cumulative allocations (alloc profiling) |
| `/debug/pprof/goroutine` | Stack dumps / leak hunt |
| `/debug/pprof/mutex` | Mutex contention (`runtime.SetMutexProfileFraction`) |
| `/debug/pprof/block` | Block profile (`runtime.SetBlockProfileRate`) |

Enable mutex/block sampling in `main` when investigating contention (low rate in prod):

```go
import "runtime"

runtime.SetMutexProfileFraction(5)
runtime.SetBlockProfileRate(1) // nanoseconds; use sparingly
```

## CLI

```bash
go tool pprof -top -alloc_objects http://localhost:8080/debug/pprof/allocs
go tool pprof -http=:8081 http://localhost:8080/debug/pprof/profile?seconds=20
go tool pprof -top cpu.prof
```

- **Flat:** cost in the function itself.
- **Cum:** function + callees — use to find entry points, then drill into flat hotspots.

## Wall-clock vs CPU

I/O-heavy services: CPU profile may look idle while goroutines block. Use **go-flamegraph** (`runtime.Stack` sampling) or goroutine profile + block profile.

## Script

`../scripts/pprof_snapshot.sh` — set `PPROF_URL` (no trailing slash on path prefix; script appends endpoints).
