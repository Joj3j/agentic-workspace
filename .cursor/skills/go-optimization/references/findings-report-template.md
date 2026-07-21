# Optimization report template

Save as `docs/actual/optimization-report.md` in the target repo unless directed otherwise.

## Severity rubric

| Level | Meaning |
|-------|---------|
| **major** | Measurable alloc/CPU/goroutine risk or unbounded resource; fix recommended before scale |
| **minor** | Clear inefficiency on warm path; fix when touching package |
| **info** | Style/micro-opt; only with benchmark proof |

## Template

```markdown
# Optimization report — <repo> — <date>

## Scope

- Packages: `internal/...`
- Method: static sweep, escape analysis, benchmarks (list which ran)
- Hypothesis: ...

## Summary

| ID | Sev | Location | Issue | Evidence | Proposal |
|----|-----|----------|-------|----------|----------|
| O-01 | major | file.go:NN | ... | grep / escape / bench | ... |

## Findings

### O-01 — <title> (major)

- **Location:** `path/file.go:line`
- **Evidence:** ...
- **Proposal:** ...
- **Expected impact:** lower B/op / fewer goroutines / ...
- **Risk:** behavior / readability
- **Verification:** `go test -bench=... -benchmem`, `-race`

### O-02 — ...

## Benchmarks added

| Benchmark | Package | Baseline (ns/op, B/op) |
|-----------|---------|-------------------------|

## Deferred / out of scope

- ...

## Skill follow-ups

- Gaps found in go-optimization skill or scripts: ...
```

Number findings `O-01`, `O-02` for PR cross-reference.
