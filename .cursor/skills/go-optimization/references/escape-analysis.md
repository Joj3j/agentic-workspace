# Escape analysis

## Command

From target module root:

```bash
go build -gcflags='-m -l' ./internal/pkg/... 2>&1 | tee /tmp/escape.log
```

`-m` prints escape decisions; `-l` disables inlining so line numbers map to source.

Skill wrapper (groups by file):

```bash
.cursor/skills/go-optimization/scripts/escape_check.sh ./internal/mergeregistry/...
```

## Common escape reasons and fixes

| Reason | Typical fix |
|--------|-------------|
| Passed to `interface{}` / fmt | Use typed API; structured zerolog fields |
| Returned `*T` where value suffices | Return `T` or keep pointer if required by API |
| Closure captures loop variable | Go 1.22+ per-iteration vars help; still avoid capturing large structs |
| Slice append unknown cap | `make([]T, 0, len(src))` |
| `fmt.Sprintf` / `strings.Join` in hot path | `strings.Builder` with `Grow` |
| Subslice passed to unknown callee | Copy to stack buffer only if profile proves it |
| `errors.New` / `fmt.Errorf` in tight loop | Predefine sentinel errors or wrap once outside loop |

## When to run

- Before optimizing a function already hot in pprof or benchmarks.
- After changing signatures that return pointers or `interface{}`.
- Not required for every PR — target hot packages only.

## Document in PR

List top 1–3 escape lines you addressed and re-run escape check on that package.
