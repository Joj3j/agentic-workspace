# Workspace agents

Use this file to choose or reference agents when working in the Go workspace.

---

## Workspace-wide config and settings

**When to use:** Apply when editing shared conventions, updating `rules.md`, changing workspace-wide standards, or when you want the AI to follow Go/communicator conventions across any repo (devicestore-devstore, comm-worker-gnmi-go, device-registry, etc.).

**What it provides:**
- Project context (module layout, config paths, logging)
- Go conventions (imports, errors, context, gRPC, tests)
- gRPC client reconnect pattern
- Proto and config conventions
- Kubernetes and Kustomize deployment

**How to use:**
- Open or @ mention the **agentic-workspace** folder so its rules are in context.
- Rules live in `agentic-workspace/.cursor/rules/` and apply when this folder is in scope.
- Human-readable summary: `agentic-workspace/rules.md`.

**Scope:** All repos under `/home/joji/Go/` that share these conventions. Repo-specific rules stay in each repo’s `.cursor/rules/` (e.g. comm-worker-gnmi-go).

---

## Cursor skills (agentic-workspace)

Shared skills live under `agentic-workspace/.cursor/skills/`. @ mention **agentic-workspace** or open these paths so the agent loads them.

| Skill | Path | Scripts dir | When to use |
|-------|------|-------------|-------------|
| **confluence-page** | `.cursor/skills/confluence-page/SKILL.md` | `.cursor/scripts/confluence/` | Create (or read+create) Confluence pages via REST scripts; same `confluence_env.sh` as confluence-read. |
| **confluence-read** | `.cursor/skills/confluence-read/SKILL.md` | `.cursor/scripts/confluence/` | **Read-only:** fetch or summarize a Confluence page by URL, title, or page ID; **same env** as confluence-page (`confluence_env.sh`). |
| **confluence-cloudnative-review** | `.cursor/skills/confluence-cloudnative-review/SKILL.md` | `.cursor/scripts/confluence/` | Fetch a Confluence page and output a cloud-native architecture review (critical / major / minor / info). For NSP HLD-style pages, checks HLD template section coverage (chapters 1–12). |
| **nsp-opensearch** | `.cursor/skills/nsp-opensearch/SKILL.md` | `.cursor/scripts/nsp-opensearch/` | NSP REST Gateway token + OpenSearch `_search` for error log rollups (Query A/B). Standalone Markdown reports via `nsp_opensearch_log_report.py`. |
| **k8s-test-client** | `.cursor/skills/k8s-test-client/SKILL.md` | `.cursor/scripts/k8s-test-client/` | Build and run Go test clients (comm-layer-server, device-registry, comm-worker-gnmi) against K8s-deployed services via SSH tunnel + kubectl port-forward. |
| **srl-config-load** | `.cursor/skills/srl-config-load/SKILL.md` | `.cursor/scripts/srl-config-load/` | Load a flat SR Linux config onto an NE with schema migration, NE ID preservation, TLS cert stripping, and template management (`tools/srl-configs/`). |
| **nsp-k8s-grafana** | `.cursor/skills/nsp-k8s-grafana/SKILL.md` | `.cursor/skills/nsp-k8s-grafana/scripts/` | Connect to NSP K8s + Grafana via the gateway. Download, review, fix, and upload dashboard JSON. Test PromQL counters against live Prometheus. Query metrics for workspace services (comm-worker-gnmi, comm-layer-server, device-registry, etc.). Use when checking NSP cluster health, fixing Grafana dashboards, or querying service metrics. |
| **perf-rca** | `.cursor/skills/perf-rca/SKILL.md` | — | Evidence-first root-cause analysis for performance and timeout issues. Blocks symptom-driven fixes (timeout tuning, probe settings) until root cause is confirmed with profiling/measurement. Use when reporting pod restarts, slow queries, or "why is X slow". |
| **go-flamegraph** | `.cursor/skills/go-flamegraph/SKILL.md` | — | Add an interactive SVG flamegraph endpoint (`GET /debug/pprof/flamegraph`) to any Go HTTP service. Wall-clock goroutine sampling, no external deps, self-contained SVG with zoom/hover/memory stats/analysis badges. Use when asked to add flamegraph, pprof flamegraph, or goroutine profiling to a Go project. |
| **mr-review** | `.cursor/skills/mr-review/SKILL.md` | `.cursor/scripts/mr-review/` | Produce a severity-classified MR review report from a GitLab MR URL or local branch reference. Reads the diff via git, identifies topic domain, pulls repo markups (HLD/LLD/source), asks for functional context, and writes R-NN findings (major/minor/info) to a Markdown report in the target repo. After user confirms, posts findings as GitLab MR discussion notes via `post_review.py`. Use when asked to review an MR, review a branch, or post review comments to GitLab. |
| **smoke-test-gnmi** | `.cursor/skills/smoke-test-gnmi/SKILL.md` | — | Run the comm-worker-gnmi parallel R/W smoke test (15 concurrent requests across 4 SRL NEs via worker_test_client case 17). Covers NE matrix (neA–neD, SRL_GNMI policy, mgmt IP:port), port-forward setup, pass/fail criteria, and troubleshooting (EOF preface timing fix). Use when asked to smoke test gNMI, verify concurrent R/W health, or run the parallel test against K8s. |
| **smoke-test-comm-layer-bulk** | `.cursor/skills/smoke-test-comm-layer-bulk/SKILL.md` | `.cursor/scripts/k8s-test-client/` (shared) | `benchmark_client`: **epipe** smoke (default) or **`-mode bulk`** SR1K+SRL via `comm-layer-server/cmd/rpc_test_client/bulkbench`, bulk-size inference, `-max-fail-streak` stop, `-sr-op delete` cleanup. **Get NE** for device-registry inventory + filters. `SMOKE_*` / flags, pass criteria, post-run tables, scaling ladder. |
| **subscription-local-dev-run** | `.cursor/skills/subscription-local-dev-run/SKILL.md` | `comm-subscription-server/cmd/subscription_test_client/scripts/` | Local-dev, non-interactive `subscription_test_client` demo: `subset-create` → wait → `subset-add` in one pane, readable/color-coded Kafka listen in another (`demo_tmux.sh`, `demo_kafka_listen.sh`, `demo_subscribe_flow.sh`, `pretty_listen.py`). `check_prereqs.sh` verifies CSS + comm-worker-gnmi are up first — **never starts them**, asks the user to. Use for demoing subscribe/Kafka flow or verifying a gNMI path-building fix end-to-end locally. |
| **drawio-diagrams** | `.cursor/skills/drawio-diagrams/SKILL.md` | — | Draw.io diagram authoring: layout (horizontal/vertical/hybrid), swimlanes, flow clarity, edge/label non-overlap, UML sequence diagrams ("sequential" = lifelines + messages), colors/styles, file naming and version workflow. Use when creating or editing `.drawio` / `.drawio.svg` files, files under `docs/**/diagrams/**`, or architecture/sequence/data-flow diagrams. |
| **smoke-run-deployer** | `.cursor/skills/smoke-run-deployer/SKILL.md` | `.cursor/scripts/smoke-run-deployer/` | RESTCONF smoke for NSP data deployer: NE discovery (`list-nes` — one-time per cluster), LAG/SDP listing, batched YANG PATCH epipe + ip-filter creation (`deploy`), async deployer status tracking (`check`), YANG PATCH remove cleanup (`cleanup`), deployer entry deletion (`delete`). Use when smoke-testing RESTCONF writes against an NSP cluster, creating/cleaning epipes and ip-filters via the data deployer. |
| **build-go-repo** | `.cursor/skills/build-go-repo/SKILL.md` | — | Build any Go repo that contains a `.go-make/` submodule (Nokia CI pipeline). Regenerate `history.diff` from the Jenkins `[jenkins]` baseline or merge-base, run tests + `gocover-cobertura`, and check delta coverage via `docker run build-unittest-coverage-delta:1`. Adds tests to reach the threshold (bounded retries). Use when the repo has `.go-make/`, fixing delta coverage failures, or running `make delta-coverage` locally. |
| **build-java-repo** | `.cursor/skills/build-java-repo/SKILL.md` | — | Build MDM Java repos using Gradle in Git Bash with Java 17. Regenerate `history.diff`, run `gradle7 deltaCoverage`, add UTs until threshold passes. |
| **gradle-mdm-java-upgrade** | `.cursor/skills/gradle-mdm-java-upgrade/SKILL.md` | — | Gradle/Java version upgrade migrations for MDM repos (clone, submodule, build.gradle transforms, branch, MR, verify build). |
| **mdm-log-analyzer** | `.cursor/skills/mdm-log-analyzer/SKILL.md` | `.cursor/skills/mdm-log-analyzer/scripts/` | Collect and analyze Nokia MDM logs from K8s or SCP/SFTP; parse MdmServer.log, detect adapter/resync/bulk/thread-pool/GC issues; produce markdown/HTML reports. |
| **mdm-patch-load** | `.cursor/skills/mdm-patch-load/SKILL.md` | — | End-to-end MDM patch workflow: local changes → Gradle build → SNAPSHOT threading → remote builds → docker/helm deploy on cluster. |
| **nsp-repo-public-migration** | `.cursor/skills/nsp-repo-public-migration/SKILL.md` | — | Prepare a private NSP Go repo for public listing: `.go-make`, Jenkinsfile (`release/3.0+`), docs, validations. Prompts for public GitLab group; after commits, guides user through Public-Project-Requirement-Checker and Teams DevOps promotion post; tracks dependent-repo updates after publish. |
| **go-optimization** | `.cursor/skills/go-optimization/SKILL.md` | `.cursor/skills/go-optimization/scripts/` | Evidence-first Go resource optimization: static anti-pattern sweep, escape analysis, pprof snapshots, benchmarks + benchstat, severity-classified reports. Prefers errgroup/semaphore over custom goroutine pools. Context-minimization rules; track runs in `plan.md`. Use when optimizing allocations, CPU/heap, or reviewing `internal/` hot paths. |
| **create-repo-arch-doc** | `.cursor/skills/create-repo-arch-doc/SKILL.md` | — | Creates an NSP architecture document for a repository following the HLD template (`arch-docs/docs/HLD/`) and optionally publishes to Confluence. Align with the component-architect agent when a PRD or arch-docs is in scope. Use when asked to create or generate an architecture document, HLD, or Confluence arch page for a repo. |
| **maintain-workspace-rules** | `.cursor/skills/maintain-workspace-rules/SKILL.md` | — | Guides adding and updating Cursor rules in workspace-settings. Use when editing `.cursor/rules`, adding a new rule, deciding workspace-wide vs repo-specific rule placement, or when asked how workspace rules are organized. |

**Script layout convention:** each skill's scripts live in a subdirectory of `.cursor/scripts/` named after the skill (e.g. `confluence/`, `nsp-opensearch/`, `k8s-test-client/`, `srl-config-load/`). Each subdirectory contains the env loader (`*_env.sh`), secrets template (`*_env.local.example` → gitignored `*_env.local`), and the runnable scripts. Source the env file before running any script in that dir.
