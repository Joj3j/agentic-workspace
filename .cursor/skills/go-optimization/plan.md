# go-optimization — plan tracker

Living document for skill evolution and per-repo optimization runs.  
Do not confuse with Cursor IDE plan files under `~/.cursor/plans/`.

## Skill roadmap

| Item | Status | Notes |
|------|--------|-------|
| SKILL.md workflow | done | measure → change → benchstat |
| references/ (pprof, escape, bench, rails, template) | done | progressive disclosure |
| scripts/ (escape, bench_delta, pprof, alloc_hotspots) | done | run from target repo root |
| go-code-rules.mdc §4b/§4c + skill pointer | done | rules vs HOW-TO split |
| AGENTS.md table row | done | |

## Per-repo runs

### comm-subscription-server (pilot)

| Step | Status | Notes |
|------|--------|-------|
| Static anti-pattern sweep | done | See `docs/actual/optimization-report.md` O-01–O-10 |
| escape_check.sh | done | mergeregistry, subscriptionservice, topic, upstream |
| PPROF_ENABLED on probe HTTP | done | `internal/http_server/http_server.go` |
| Benchmarks (merge, registry, router) | done | 4 bench files under internal/ |
| docs/actual/optimization-report.md | done | O-NN findings |

### Follow-up repos (out of scope for pilot)

- comm-layer-server
- comm-worker-gnmi-go
- device-registry
- comm-client-go / comm-client-gnmi-go

## Skill improvements from pilots

- Consider `static_sweep.sh` with standard grep patterns for NSP `internal/`.
- Document kustomize key for `PPROF_ENABLED` when enabling in lab clusters.

## Shipped / deferred (pilot)

**Shipped:**

- `go-optimization` skill + scripts + references + `plan.md`
- `go-code-rules.mdc` §4b, §4c, skill pointer, context-minimization bullet
- `AGENTS.md` skill row
- CSS: pprof gate, timer reuse (registry lookup + NE watcher), `grpcTarget` cache, `pathsNotIn` presize, benchmarks, optimization report

**Deferred:**

- O-01 merge allocation refactor (needs load + alloc profile)
- O-05 request ID micro-opt
- O-07 mediation cache bounds policy
- O-08 subscribe_merge error formatting
- Cross-repo runs (comm-layer-server, worker-gnmi, device-registry)
