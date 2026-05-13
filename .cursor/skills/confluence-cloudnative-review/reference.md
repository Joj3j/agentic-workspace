# Extended cloud-native review dimensions

Use this as a **scan list** after the minimum dimensions in `SKILL.md`. For each line: if the page discusses the topic, review it; if the page is silent but the system clearly needs it, add an **Open question** — do not invent details.

## Resilience and lifecycle

- Pod disruption budgets, rolling update strategy, maxUnavailable / maxSurge
- Graceful shutdown: `preStop`, drain time, in-flight request completion
- Timeouts, retries, idempotency, circuit breakers / bulkheads between services
- Rate limiting and backpressure (HTTP, gRPC, message consumers)
- Dead letter queues, poison messages, ordering guarantees (if messaging)
- Multi-AZ / multi-region, failover, RTO/RPO (if stated or implied)

## Storage and state

- Ephemeral vs persistent volumes; resize, snapshot, backup/restore
- StatefulSet vs Deployment; read/write affinity
- Object storage access pattern (signed URLs, IAM)

## Configuration and releases

- ConfigMaps / Secrets: rotation, versioning, least privilege
- Feature flags vs config drift across environments
- Database migrations: ordering with app rollout, rollback story

## Security (beyond RBAC)

- NetworkPolicies, egress controls, service mesh policy (if mentioned)
- Image provenance, signing, base image updates
- PII / encryption at rest and in transit, key management
- Audit logs and admin access paths

## Observability depth

- RED/USE or equivalent golden signals for **this** service
- Trace propagation across pod boundaries
- Log volume, cardinality, PII in logs

## CI/CD and platform

- How images are built, scanned, and promoted
- GitOps vs imperative deploys (if relevant to the doc)
- Resource quotas / LimitRanges at namespace level

## APIs and clients

- Versioning, compatibility, deprecation
- Pagination, filtering, max payload size
- Idempotent writes, optimistic concurrency (ETags, versions)

## Cost and efficiency

- Autoscaling bounds, idle cost, expensive dependencies (GPU, large nodes)

## Compliance and data

- Data residency, retention, right-to-delete (if product context suggests it)

---

## “Often missed” on design pages

These are **frequent gaps** in wiki designs; use as **questions** when applicable:

1. **End-to-end timeout budget** — who enforces deadline across hops?
2. **Behavior under partial failure** — one dependency down: degrade, fail closed, or queue?
3. **Cache stampede / thundering herd** — single-flight, jitter, TTL strategy
4. **Cold start / scale-from-zero** — latency impact if used
5. **Connection pool sizing** — DB and HTTP client limits per pod × replicas
6. **Leader election or split-brain** — if multiple writers or controllers
7. **Clock skew** — if ordering or TTL depends on time
8. **Test data / prod parity** — how load tests relate to prod topology
