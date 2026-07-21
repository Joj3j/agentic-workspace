# Automated benchmarking

## Goals

- Prove a change improves or does not regress ns/op and B/op.
- Avoid optimizations that add complexity without measurable gain.

## Write benchmarks

Place `BenchmarkXxx` in `*_test.go` next to the hot code.

```go
func BenchmarkMergePaths(b *testing.B) {
    cases := []struct {
        name string
        n    int
    }{{"small", 8}, {"large", 256}}
    for _, tc := range cases {
        b.Run(tc.name, func(b *testing.B) {
            in := makeTestInput(tc.n)
            b.ReportAllocs()
            b.ResetTimer()
            for i := 0; i < b.N; i++ {
                _ = mergePaths(in)
            }
        })
    }
}
```

- `b.ReportAllocs()` — surfaces allocs/op in output.
- `b.ResetTimer()` — after expensive setup.
- Keep setup outside the loop; use sub-benchmarks for sizes.

## Run

```bash
go test -bench=BenchmarkMergePaths -benchmem -count=10 -run=^$ ./internal/pkg/...
```

Install `benchstat` if missing: `go install golang.org/x/perf/cmd/benchstat@latest`

## Compare revisions

```bash
scripts/bench_delta.sh -pkg ./internal/pkg -bench BenchmarkMergePaths -count 10 -base origin/master
```

Interpret: significant **+** on time or allocs is a regression unless explained.

## When NOT to optimize early

- No `benchmem` / alloc profile evidence for the path.
- Replacing `encoding/json` globally — only fixed-schema inner loops.
- `sync.Pool` without proof — pools add complexity and GC coupling.
- Readability loss in non-hot code for marginal savings.

These rules mirror workspace **go-code-rules.mdc** §4a; the skill owns measurement HOW-TO.

## After optimization

1. `benchstat` old vs new.
2. `go test -race ./internal/pkg/...`
3. In `.go-make` repos: `make test` or build-go-repo delta check if lines changed.
