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
