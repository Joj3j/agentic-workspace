# Agentic workspace

Shared Cursor AI configuration for all repos in the Go workspace. Add this repo as the **first folder** in your `.code-workspace` so its rules, skills, and commands are always in scope.

Synced from `workspace-settings`; use either folder as the config source — keep them in sync when rules or skills change.

## Getting started

```bash
git clone git@github.com:Joj3j/agentic-workspace.git
```

## Usage

### In the IDE

1. Open your `.code-workspace` file with `agentic-workspace` listed as the first folder.
2. Reference any file with `@agentic-workspace/...` from agent chat in any sibling repo.

### Rules (auto-applied)

| Rule | Scope | Trigger |
|------|-------|---------|
| `workspace-wide.mdc` | All repos | Always (no globs) — project layout, gRPC reconnect, proto, Kustomize |
| `go-code-rules.mdc` | Go | `**/*.go` |
| `rust-code-rules.mdc` | Rust | `**/*.rs`, `**/Cargo.toml` |
| `java-code-rules.mdc` | Java | `**/*.java`, `**/pom.xml`, `**/build.gradle` |
| `python-code-rules.mdc` | Python | `**/*.py`, `**/pyproject.toml`, `**/requirements*.txt` |

Draw.io diagram guidance lives in the **drawio-diagrams** skill (not a rule).

### Commands

| Command | How to invoke | What it does |
|---------|--------------|--------------|
| **MR** | `@agentic-workspace/.cursor/commands/mr.md` | Branch from master, commit, push, open MR |

### Skills

See **AGENTS.md** for the full skills table (Confluence, k8s test clients, smoke tests, MR review, build pipelines, MDM tools, perf-rca, etc.).

### Script setup (first time)

Each script directory has an `*_env.local.example` → copy to `*_env.local` (gitignored), then `source *_env.sh`. See `.cursor/scripts/README.md`.

## Arch doc convention

Architecture documents live under each **target repo's own `docs/`** — not here. Use the **create-repo-arch-doc** skill. See `docs/README.md` for repos that already have arch docs.

## Repo-specific rules

Keep repo-specific Cursor rules in each repo's `.cursor/rules/*.mdc`. Do not duplicate workspace-wide conventions in individual repos.
