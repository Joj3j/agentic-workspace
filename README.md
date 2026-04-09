# Agentic workspace

Shared Cursor AI configuration for all repos in the Go workspace. Add this repo as the **first folder** in your `.code-workspace` so its rules, skills, and commands are always in scope. Cloned from workspace-settings.

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
| `drawio-rules.mdc` | Diagrams | `**/*.drawio`, `**/docs/**/diagrams/**` |

### Commands

| Command | How to invoke | What it does |
|---------|--------------|--------------|
| **MR** | `@agentic-workspace/.cursor/commands/mr.md` | Branch from master, commit, push, open MR |
| **Confluence read** | `@agentic-workspace/.cursor/commands/confluence-read.md` | Read a Confluence page by title/URL/ID |

### Skills

| Skill | What it does |
|-------|-------------|
| **confluence-page** | Read or create Confluence pages via REST API scripts. Handles env setup, URL parsing, parent page lookup. |
| **create-repo-arch-doc** | Generate an HLD architecture document (markdown + Confluence HTML + draw.io diagrams) for any repo. Outputs go under the target repo's `docs/` directory. |
| **maintain-workspace-rules** | Guide for adding or updating rules in this repo — placement decisions, frontmatter format, checklist. |

### Confluence scripts (first-time setup)

```bash
cd agentic-workspace/.cursor/scripts
cp confluence_env.local.example confluence_env.local
# Edit confluence_env.local: set CONFLUENCE_BASE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN
source confluence_env.sh
```

Then in the same shell, run `confluence_read_page.py` or `confluence_create_page.py`. See `.cursor/scripts/README.md` for full usage.

## Arch doc convention

Architecture documents live under each **target repo's own `docs/`** — not here. Standard layout:

```
<repo>/docs/
  confluence/
    body.html                    # Confluence page body (HTML)
    diagrams/                    # draw.io files for Confluence upload
  actual/
    System_Design_HighLevel.md   # Detailed local HDD (markdown)
```

Use the **create-repo-arch-doc** skill to generate these. See `docs/README.md` for repos that already have arch docs.

## Repo-specific rules

Keep repo-specific Cursor rules in each repo's `.cursor/rules/*.mdc`. Do not duplicate workspace-wide conventions in individual repos.
