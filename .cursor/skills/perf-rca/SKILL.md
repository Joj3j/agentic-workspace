---
name: perf-rca
description: >-
  Systematic root-cause analysis for performance and timeout issues in
  distributed/microservice systems (Go, Rust, gRPC, Kubernetes). Guides
  evidence-first diagnosis: data-path tracing, profiling, hypothesis ranking,
  and measurement-gated fixes. Use when the user reports: pod restarts, timeout
  errors, slow queries, high CPU, requests hanging, or asks "why is X slow /
  failing". Do NOT skip to fixes — request evidence first.
---

# Performance Root-Cause Analysis

## Core Principle

**Anchor on the data path, not the failure mode.**

A timeout is a symptom. A pod restart is a symptom. The root cause is always
somewhere in the path the data travels. Start there.

---

## Step 1 — State the data path before forming hypotheses

Before any code is read, trace the full path of the request end-to-end:

```
Client → [service A] → [service B] → [library] → [NE/DB/external]
```

Ask: at which hop does time actually get consumed? Require evidence for the
answer — do not assume.

**Blocking question to ask the user:**
> "Which component produces the slow response — the caller sees a timeout, but
> does the callee finish fast or slow? Check logs with timestamps at each hop."

---

## Step 2 — Rank hypotheses by data-path location

List 3–5 hypotheses ordered by proximity to the observed slowdown in the data
path. For each, state:

- What evidence would **confirm** it
- What evidence would **rule it out**

Template:
```
H1: [component/layer] — [proposed mechanism]
  Confirm: [observable metric or log line]
  Rule out: [counter-evidence]
```

**Do not propose a fix until one hypothesis reaches CONFIRMED.**

---

## Step 3 — Gather evidence before touching code

Request this data in priority order. Stop and ask the user — do not invent it.

### For slowness / timeouts

| Evidence | How to get it |
|----------|--------------|
| Log timestamps at each service boundary | `kubectl logs <pod> --since=10m` |
| CPU profile during the slow operation | Rust: `perf record`, Go: `pprof /debug/pprof/profile` |
| Whether the same query succeeds on another client/system | Run it manually |
| Message sizes (bytes received, bytes parsed) | Add a single log line with size |
| Whether slowness is proportional to response size | Try smaller vs larger path |

### For pod restarts / OOM

| Evidence | How to get it |
|----------|--------------|
| Pod event reason | `kubectl describe pod <name>` |
| Liveness/readiness probe failure details | Same as above |
| Memory usage at restart | `kubectl top pod` or metrics |
| Last log lines before restart | `kubectl logs --previous` |

### For O(N²) / algorithmic issues (key pattern)

Ask: **does execution time grow proportionally to response size, or faster?**

```
small path (100 items) → Xs
medium path (1000 items) → Ys   # if Y >> 10×X → likely quadratic
large path (10000 items) → Zs
```

If yes: look for any loop that re-processes previously seen data
(re-scanning a buffer, re-parsing a message, re-traversing a collection).

---

## Step 4 — Prohibitions until root cause is confirmed

Do **not** do any of the following until Step 2 has a CONFIRMED hypothesis:

- Change timeout values (client, server, read, connect)
- Adjust Kubernetes probe periods or thresholds
- Change thread/goroutine pool sizes
- Add retry logic
- Increase resource limits (CPU, memory)

These are symptom treatments. They mask the root cause and produce the next
symptom.

---

## Step 5 — Require a measurement for any fix

Before implementing a fix, state:

> "The fix is correct if [metric] changes from [before] to [after].
> I will not claim success until that measurement is observed."

Examples of valid measurements:
- "Request latency for path X drops from 20 min to < 30 s"
- "CPU profile shows function F no longer dominates"
- "Bytes-decoded per second increases by ~N×"

A timeout going from fail to pass is **not** a measurement — it may mean the
timeout was increased, not that the root cause was fixed.

---

## Step 6 — Distinguish library vs. application bugs

When a library is on the data path, read its decode/encode/transport code
**before** concluding the application code is the problem.

Checklist:
- [ ] Is the library stateless where it should be stateful? (e.g. re-scanning a
      buffer from byte 0 on every call → O(N²))
- [ ] Does it buffer the full response before yielding to the caller?
- [ ] Does it copy data unnecessarily on each chunk arrival?

If the library is external/vendored: check its changelog and recent commits for
performance fixes before writing workarounds.

---

## Decision tree

```
User reports: slow / timeout / restart
        │
        ▼
Is the same operation fast on another system/client?
  Yes → problem is in THIS system's data path
  No  → problem may be in the NE/DB/external, or in shared infra
        │
        ▼
Add timestamps at each service boundary. Where does time accumulate?
        │
        ▼
Does the slowness scale with response size?
  Yes → algorithmic issue (O(N²), buffering, lazy decode)
  No  → fixed overhead (connection setup, auth, schema load, DNS)
        │
        ▼
Confirm hypothesis with a profiler or a targeted log line.
        │
        ▼
Fix only the confirmed cause. Measure before and after.
```

---

## Reference: past cases

See [cases.md](cases.md) for annotated examples of confirmed root causes and
how they were found.
