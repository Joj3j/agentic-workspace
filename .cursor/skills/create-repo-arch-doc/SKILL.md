---
name: create-repo-arch-doc
description: Creates an NSP architecture document for a repository following the HLD template (arch-docs/docs/HLD/) and optionally publishes to Confluence. Use when the user asks to create or generate an architecture document, HLD, or Confluence arch page for a repo. Align with the component-architect agent when a PRD or arch-docs is in scope.
---

# Create repository architecture document (HLD / Confluence)

Use this skill when creating an **architecture document** (HLD) for a repo. The **canonical structure** is the HLD chapter template in **arch-docs** (`docs/HLD/`), which matches the NSP Confluence template (pageId 2162422282). **Create new Confluence arch pages under parent page 2069174542** (not under the template). Output can be (a) markdown HLD in the repo, (b) a Confluence page in NSP Arch Evo, or both.

**Agent alignment:** The **component-architect** agent (`arch-docs/.cursor/agents/component-architect.md`) is used for this generation when working from a PRD. When the user invokes component-architect or when arch-docs is in scope, follow that agent's workflow (PRD under `docs/PRD/` → HLD from `docs/HLD/` templates) and use this skill for structure, Confluence publish, and repo HLD layout.

**Gold-standard reference:** The **Device Registry** arch page (`device-registry/docs/confluence/body.html` for Confluence body, `device-registry/docs/actual/System_Design_HighLevel.md` for detailed local HDD, `device-registry/docs/confluence/diagrams/` for draw.io) demonstrates the expected depth, table formats, API detail, and draw.io usage for all sections. Use it as the model when generating new arch documents.

## Canonical structure: arch-docs HLD

The section order and content expectations come from **arch-docs**:

| # | Chapter file | Title | Expected table formats |
|---|--------------|--------|------------------------|
| 0 | `index.md` | Overview + contents | Contents list (links to 01–12) |
| 1 | `01-architecture-overview.md` | Architecture Overview | — (narrative + component diagram link) |
| 2 | `02-components.md` | Components | Component list (bullet or table: Name, Role, Proto/Port) |
| 3 | `03-foss-3pp-components.md` | Key FOSS/3PP Components | Dependency table: Package, Version, Purpose |
| 4 | `04-system-dependencies.md` | System Dependencies | Dependency table: System, Protocol, Config keys, Notes |
| 5 | `05-apis.md` | APIs | **Detailed** — see [API section structure](#api-section-structure-chapter-5) |
| 6 | `06-models.md` | Models | Data model tables: Field, Type, Description; etcd/storage key patterns |
| 7 | `07-data-flow.md` | Data Flow | draw.io diagram link; narrative per ingest/read/notify path |
| 8 | `08-security-access-control.md` | Security and Access Control | TLS config table: Connection, Endpoint, TLS behaviour |
| 9 | `09-platform-considerations.md` | Platform Considerations | HA/DR/Scaling/Deployment subsection tables |
| 10 | `10-resource-usage.md` | Resource Usage | **Detailed** — see [Resource usage tables](#resource-usage-tables-chapter-10) |
| 11 | `11-patents.md` | Patents | — |
| 12 | `12-sign-off.md` | Sign-Off | — |

- **Template source:** `arch-docs/docs/HLD/` (NN-*.md). Each file has C1/C2 phase guidance in blockquotes; use that to decide what to write.
- **Confluence template (same structure):** https://confluence.ext.net.nokia.com/pages/viewpage.action?pageId=2162422282  
- **Sample filled page:** https://confluence.ext.net.nokia.com/display/NSPArchEvo/gNMI+Communicator+Service  
- **Device Registry arch page:** https://confluence.ext.net.nokia.com/display/NSPArchEvo/Device+Registry+Arch  

See [reference.md](reference.md) for chapter purposes, table templates, API patterns, draw.io generation, and diagram notes.

### Documentation guidelines (arch-docs)

Follow **`arch-docs/docs/documentation-guidelines.md`** in full. In practice:

| Topic | Expectation |
|-------|-------------|
| **Backstage / TechDocs** | Repo docs published via TechDocs; structure aligns with mkdocs-style navigation where applicable. |
| **mkdocs** | Use the layout and conventions described in documentation-guidelines (paths, nav). |
| **`catalog-info.yaml`** | Register the component; in **`metadata.links`**, include the **Confluence architecture page** URL once the page exists so Backstage and the wiki stay linked. |
| **Diagrams in repo** | Use **Mermaid** in markdown under `docs/` (e.g. `docs/HLD/`, `docs/actual/`). Confluence uses **draw.io** for upload; keep both consistent in meaning. |
| **Living HLD** | Update HLD and Confluence summary when features or integrations change; do not leave arch docs stale relative to production behavior. |

### Confluence body and HLD section coverage

The **Confluence** `body.html` (and any single-page arch wiki view) must **cover the same section areas** as the HLD template (`arch-docs/docs/HLD/index.md` chapters 1–12): Architecture Overview, Components, FOSS/3PP, System Dependencies, APIs, Models, Data Flow, Security and Access Control, Platform Considerations, Resource Usage, Patents, Sign-Off. Use the **same order** as the Confluence template (pageId 2162422282) where possible.

- For each area: at least a short paragraph, bullets, or a table — or an explicit **N/A** / **TODO** with owner.
- Do not omit whole chapters from the wiki body because the detailed write-up lives only in repo markdown; the wiki is what many reviewers read first.
- **Reviews:** The [confluence-cloudnative-review](../confluence-cloudnative-review/SKILL.md) skill checks cloud-native concerns **and** whether these template sections appear on the fetched Confluence page (gaps → findings or open questions).

## Output layout (per repo)

All arch doc outputs live under the **target repo's own `docs/` directory** — not in workspace-settings. Standard layout:

```
<repo>/docs/
  confluence/
    body.html                            # Confluence page body (HTML)
    diagrams/                            # draw.io files for Confluence upload
      <repo>_components_v1.drawio
      <repo>_data_flow_v1.drawio
  actual/                                # Detailed local HDD (markdown)
    System_Design_HighLevel.md
    ETCD_Integration_Summary.md          # (if applicable)
    Kafka_Integration_Summary.md         # (if applicable)
```

Every arch doc can produce **two outputs** at different depths:

| Output | Location | Depth | Audience |
|--------|----------|-------|----------|
| **Confluence body** (`body.html`) | `<repo>/docs/confluence/body.html` | Concise (~100–200 lines HTML). One paragraph per section, bullet lists for components/deps/APIs, draw.io placeholder links, resource summary table. | Architects, stakeholders browsing Confluence. |
| **Local HDD** (markdown) | `<repo>/docs/actual/System_Design_HighLevel.md` or `<repo>/docs/HLD/` chapters | Detailed (~500–800 lines). Full Mermaid diagrams, field-level API tables with samples, config tables, storage key patterns, integration summaries. | Developers, on-call engineers, reviewers. |

When generating, produce **both** unless the user specifies otherwise. The Confluence body is a summary; the local HDD is the authoritative reference.

## Two modes

### Mode A: From PRD (component-architect style)

- **When:** User has a PRD (e.g. under `docs/PRD/`) or is using the component-architect agent.
- **Steps:**
  1. Read the PRD and `arch-docs/docs/HLD/` chapter templates (and `arch-docs/docs/documentation-guidelines.md`).
  2. For each HLD chapter (01–12), draft content per the template's C1/C2 notes; ask the user when input is missing.
  3. Store the HLD in the repo under `docs/HLD/` (same filenames: `index.md`, `01-architecture-overview.md`, …) as per documentation guidelines.
  4. Optionally publish to Confluence (single summary page or link to local HLD); see "Confluence publish" below.

### Mode B: From existing repo (no PRD)

- **When:** User wants an arch document for an existing repo without a PRD.
- **Steps:**
  1. Optionally fetch Confluence template and sample (see "Confluence access" below) to confirm section order; otherwise use the HLD chapter list above.
  2. Analyze the repo: README, docs, `cmd/`, `internal/`, configs, go.mod, Kustomize, proto files, etc. Infer purpose, components, APIs, deployment, data flow. **Critical:** Follow the [Dependency verification](#dependency-verification-anti-hallucination) rule — read `go.mod` of key wrapper libraries (e.g. `comm-client-go`) to verify actual integrations before documenting system dependencies or data flow paths.
  3. Draft each section (01–12) from repo content. Use the table formats specified in the canonical structure table above and detailed in [reference.md](reference.md). For sections that cannot be filled, keep the **heading** and add: `*TODO: [what to add or who should fill].*`
  4. Output as (a) markdown under `docs/actual/` or `docs/HLD/` in the repo, and/or (b) a single Confluence page (see below). Follow documentation-guidelines (e.g. Mermaid for diagrams in repo docs).
  5. Generate **draw.io diagrams** directly for component and data flow diagrams (see [Draw.io diagram generation](#drawio-diagram-generation) below).

## Dependency verification (anti-hallucination)

When documenting system dependencies, component integrations, and data flow paths, **always verify from actual dependency manifests** — never assume based on historical knowledge or transitive dependency presence.

### Mandatory checks

1. **Read the repo's `go.mod` / `Cargo.toml` / `package.json`** — identify direct vs indirect dependencies. Indirect/transitive deps do NOT prove the repo uses that system directly.
2. **Read the `go.mod` of key wrapper libraries** (e.g. `comm-client-go`, `comm-shared-go`) — these evolve independently. A library that historically used RabbitMQ may now use a completely different integration (e.g. `comm-operator-client-protobuf-go` for gRPC-based worker tracking). Always check the wrapper's own dependency manifest to confirm what it actually uses.
3. **Cross-reference with source code** — grep for actual import paths and usage in `internal/` or `src/`. A dependency in `go.mod` as `// indirect` means the repo does not import it directly; trace which direct dependency pulls it in and verify the integration path.
4. **Do not infer integration from package names alone** — e.g. `rabbitmq/amqp091-go` appearing as an indirect dep does not mean the service uses RabbitMQ. It may be a leftover transitive dependency from a library that has since migrated away from RabbitMQ.

### What to document

| Dependency type | How to verify | Document as |
|----------------|---------------|-------------|
| **Direct import** (in repo source) | `go.mod` require + grep for import path in `internal/` | System dependency (Ch 4), component (Ch 2) |
| **Direct dep of a wrapper lib** | Read the wrapper lib's `go.mod` | Mention in component description ("via `<wrapper>`") |
| **Indirect/transitive only** | Listed as `// indirect` in `go.mod` | Note in Ch 3 FOSS table as transitive; do NOT list as a system dependency |
| **Removed/replaced** | Absent from direct deps; present only as stale transitive | Do NOT document as an active integration |

### Example: comm-client-go

Before documenting what the Universal Dispatcher uses for worker dispatch:
1. Read `comm-client-go/go.mod` — check direct `require` block
2. If `comm-operator-client-protobuf-go` is listed → document "Comm Operator gRPC dispatch"
3. If `rabbitmq/amqp091-go` appears only as `// indirect` → do NOT document RabbitMQ as the dispatch mechanism
4. Verify by reading comm-client-go source if unclear

## API section structure (Chapter 5)

The API section should be the most detailed part of the arch document. Follow the Device Registry pattern with sub-sections per gRPC service.

### Local HDD (detailed)

For each gRPC service, produce:

1. **RPC table** — one row per RPC:

| RPC | Request | Response | Purpose |
|-----|---------|----------|---------|
| `GetNeId` | `GetNeIdRequest` | `GetNeIdResponse` | Look up NE by address:port |

2. **Message abstracts** — bullet list per message with field name, type, and short description.

3. **Request detail tables** — for complex requests (e.g. create vs update semantics):

| Field | Type | Create (new) | Update (existing) |
|-------|------|--------------|-------------------|
| `ne_id` | string | Required | Required |
| `endpoints` | repeated NeEndpoint | At least one | Optional |

4. **Sample payloads** — JSON representation of gRPC messages (create, update, delete examples).

5. **Notification stream samples** — for services with server-streaming RPCs, show sample payloads for each event type (CREATE, UPDATE, DELETE) and each message type.

### Confluence body (concise)

For the Confluence body, compress to:
- Bullet list of services and their RPCs (one line per RPC).
- Link to proto files for full details.
- One sentence per service summarizing purpose.

### Proto-to-doc workflow

1. Read all `.proto` files in `protomsg/` or `protobuf/`.
2. For each `service`, extract RPCs, request/response types, streaming mode.
3. For each message, extract fields with types and any `optional`/`repeated`/`oneof` qualifiers.
4. Cross-reference with `internal/` implementation for create-vs-update semantics, validation rules, and side effects (e.g. notifications emitted).
5. Generate sample JSON payloads by filling each field with realistic values from the repo's domain.

## Resource usage tables (Chapter 10)

### K8s resource table

Extract from `kustomize/base/deployment.yaml`:

| Resource | Requests | Limits |
|----------|----------|--------|
| Memory | (from spec) | (from spec) |
| CPU | (from spec) | (from spec) |

### Runtime footprint tables (per subsystem)

For each significant subsystem (e.g. Kafka consumer, RESTCONF client, gRPC server), add a footprint table:

| Resource | Value | Notes |
|----------|-------|-------|
| Goroutines | (count) | (breakdown) |
| Memory (steady-state) | (range) | (what dominates) |
| CPU (idle / per-op) | (range) | (what triggers) |
| Network | (range/msg) | (protocol/direction) |

### Storage estimates

For services with persistence (etcd, DB), add a projection table:

| Metric | Projected |
|--------|-----------|
| Scale factor | (e.g. 50K NEs / 10K baseline) |
| Projected DB size | (extrapolated) |
| Quota usage | (% of default) |
| Key/row count | (count) |

## Draw.io diagram generation

Generate draw.io diagrams **directly** as `.drawio` XML files — do not require Mermaid as an intermediate step. Follow the **drawio-diagrams** skill (`workspace-settings/.cursor/skills/drawio-diagrams/SKILL.md`) for all styling. Store diagrams under `<repo>/docs/confluence/diagrams/`.

### Component diagram (direct draw.io)

Generate a **flowchart-style** `.drawio` file with:

- **Container rectangle** for the main service (e.g. "DEVICE REGISTRY") — `UPPERCASE`, bold, `fontSize=14`, `align=center`.
- **Child component shapes** inside the container — rounded rectangles, 120×80px, light fills per category (see the **drawio-diagrams** skill component colors).
- **External subgraphs** — group Clients, Data Sources, Persistence, Consumers as separate regions.
- **Connectors** — `strokeColor=#2c5282`, `strokeWidth=2`, `edgeStyle=orthogonalEdgeStyle`; edge labels with `labelBackgroundColor=#ffffff`, `fontColor=#333333`.
- **Vertices before edges** in XML for correct rendering.
- **Naming:** `<repo>_components_v1.drawio`.

### Data flow diagram (direct draw.io — sequence)

Generate a **UML sequence diagram** `.drawio` file with:

- **Lifelines** — `shape=umlLifeline`, `strokeWidth=4`, `strokeColor=#2c5282`; callers in `#ffe6cc` (orange), service in `#d5e8d4` (green), storage in `#e8f4e8` (light green).
- **Messages** — `edgeStyle=elbowEdgeStyle`, `elbow=vertical`, `endArrow=block`, `strokeWidth=2`; labels with `labelBackgroundColor=#ffffff`, `fontColor=#000000`.
- **Self-calls** — `curved=1` with two waypoints for notify/internal operations.
- **Dashed edges** for async/streaming paths.
- **Lifeline order** — left-to-right by request flow (e.g. callers → service → external → storage → consumers).
- **Naming:** `<repo>_data_flow_v1.drawio`.

Reference implementation: `device-registry/docs/confluence/diagrams/device_registry_data_flow_v1.drawio` — 6 lifelines (Discovery_Service, Device_Registry, Device_Admin, Kafka, etcd, Clients), messages for RESTCONF sync, Kafka events, gRPC registration, read/write, watch events, and SubscribeNotifications.

### Referencing diagrams in the arch doc

In `body.html` (Confluence):
```html
<p><em>Component diagram:</em> <a href="diagrams/<repo>_components_v1.drawio">draw.io</a> (skill: <code>.cursor/skills/drawio-diagrams/SKILL.md</code>). In Confluence: Insert &rarr; draw.io and upload the diagram.</p>
```

In local HDD (markdown):
```markdown
*Component diagram:* [<repo>_components_v1.drawio](diagrams/<repo>_components_v1.drawio) (draw.io; skill: `.cursor/skills/drawio-diagrams/SKILL.md`).
```

### When to generate which diagrams

| Diagram type | When to generate | Naming |
|-------------|-----------------|--------|
| **Component** | Always (Ch 2) | `<repo>_components_v1.drawio` |
| **Data flow (sequence)** | Always (Ch 7) | `<repo>_data_flow_v1.drawio` |
| **Startup / sync sequence** | When the service has startup sync (e.g. RESTCONF, Kafka) | `<repo>_startup_sync_v1.drawio` |
| **NBI/SBI swimlane** | When the service sits between NBI clients and SBI workers | `<repo>_nbi_sbi_v1.drawio` |
| **Async ticket lifecycle** | When the service handles async/batch operations | `<repo>_async_lifecycle_v1.drawio` |

## Confluence publish

- **Prerequisites:** In the same terminal used for scripts, run:  
  `cd <workspace-settings>/.cursor/scripts && source confluence_env.sh`  
  (Requires `confluence_env.local` with `CONFLUENCE_BASE_URL`, `CONFLUENCE_USERNAME`, `CONFLUENCE_API_TOKEN`.)

- **Read template/sample (optional):**  
  `python3 confluence_read_page.py --page-id 2162422282 --format text`  
  `python3 confluence_read_page.py --title "gNMI Communicator Service" --space-key NSPArchEvo --format text`

- **Create page:** Single Confluence page with all sections in one body (HTML), or a short summary + "See repo docs/HLD/".  
  `python3 confluence_create_page.py --parent-id 2069174542 --space-key NSPArchEvo --title "<Page Title>" --body-file <repo>/docs/confluence/body.html`  
  Or `--body` with inline HTML. Create new arch pages under parent **2069174542**; use `--parent-title` only if a different parent is required.

- **Diagrams in Confluence:** Upload draw.io files via Confluence UI (Insert → draw.io) after page creation. In the HTML body, include a link placeholder and instruction text. Do not use Mermaid in Confluence bodies — use draw.io only.

## Section fill rule

For any section that cannot be filled: keep the **section heading** and add a short note:  
`*TODO: [what to add or who should fill].*`  
Do not omit the section.

## Clarifications to ask when needed

- **Output:** Repo HLD only, Confluence only, or both?
- **Output level:** Concise Confluence body, detailed local HDD, or both?
- **Parent page:** Under which Confluence page (e.g. "MDC Wrapper Server") or parent page ID?
- **Page title:** Exact Confluence title (e.g. "Device Registry Arch").
- **Source:** PRD available (use component-architect flow) or analyze repo only?
- **Diagrams:** Generate draw.io directly, or Mermaid only for repo docs?
- **API depth:** Full proto-to-doc with samples, or summary only?

## Sample repos (arch docs in each repo's docs/)

Each repo owns its arch docs under its own `docs/` directory:

| Repo | Confluence body | Local HDD | Diagrams | Notes |
|------|----------------|-----------|----------|-------|
| **device-registry** | `docs/confluence/body.html` | `docs/actual/System_Design_HighLevel.md` | `docs/confluence/diagrams/device_registry_data_flow_v1.drawio` | **Gold-standard**: full API tables, sequence diagrams, Kafka/etcd integration summaries, resource projections, production draw.io. |
| **comm-layer-server** | `docs/confluence/body.html` | — | `docs/confluence/diagrams/comm_layer_server_components_v1.drawio`, `comm_layer_server_data_flow_v1.drawio` | Full Confluence body with API tables, component + data flow draw.io diagrams. Uses Comm Operator (not RabbitMQ) for worker dispatch. |

- Create pages under parent 2069174542: `--parent-id 2069174542 --body-file <repo>/docs/confluence/body.html`.
- New repos: create `<repo>/docs/confluence/body.html` and optionally `<repo>/docs/confluence/diagrams/`, `<repo>/docs/actual/`.

## References

| Resource | Location | Purpose |
|----------|----------|---------|
| HLD chapter templates | `arch-docs/docs/HLD/` (index + 01–12) | Section order, C1/C2 guidance |
| Component-architect agent | `arch-docs/.cursor/agents/component-architect.md` | PRD → HLD workflow |
| Documentation guidelines | `arch-docs/docs/documentation-guidelines.md` | Backstage techdocs, mkdocs, Mermaid, catalog-info |
| Draw.io diagrams skill | `workspace-settings/.cursor/skills/drawio-diagrams/SKILL.md` | Naming, colors, layout, sequence diagrams, versioning |
| Confluence scripts | `workspace-settings/.cursor/scripts/` | `confluence_env.sh`, `confluence_read_page.py`, `confluence_create_page.py` |
| Confluence template | pageId **2162422282** | Structure reference (do not create under) |
| Parent for new pages | pageId **2069174542** | `--parent-id` for `confluence_create_page.py` |
| Device Registry arch | [Confluence](https://confluence.ext.net.nokia.com/display/NSPArchEvo/Device+Registry+Arch), `device-registry/docs/confluence/body.html` | Gold-standard reference |
| gNMI Communicator arch | [Confluence](https://confluence.ext.net.nokia.com/display/NSPArchEvo/gNMI+Communicator+Service) | Earlier sample page |
| Detail and diagram notes | [reference.md](reference.md) | Table templates, API patterns, draw.io generation |
