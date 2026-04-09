---
name: maintain-workspace-rules
description: Guides adding and updating Cursor rules in agentic-workspace. Use when editing .cursor/rules, adding a new rule, deciding workspace-wide vs repo-specific rule placement, or when asked how workspace rules are organized.
---

# Maintain workspace rules

Use this skill when working in **agentic-workspace** or when the user asks about workspace rules, adding rules, or where conventions live.

## Where rules live

| Location | Purpose |
|----------|---------|
| **agentic-workspace/.cursor/rules/** | Workspace-wide rules; apply when this folder is in scope (e.g. multi-root workspace). |
| **Each repo’s .cursor/rules/** | Repo-specific rules (e.g. comm-worker-gnmi-go project-overview); do not duplicate workspace content here. |

## Rule files in this repo

| File | Applies to | Notes |
|------|------------|--------|
| `workspace-wide.mdc` | All Go/communicator repos | Layout, config, gRPC reconnect, proto, Kustomize. No globs → always in context when agentic-workspace is open. |
| `go-code-rules.mdc` | Go only | Style, errors, API design, zerolog logging. `globs: ["**/*.go"]`. |
| `rust-code-rules.mdc` | Rust only | Performance, idioms, errors, async. `globs: ["**/*.rs", "**/Cargo.toml", "**/Cargo.lock"]`. Includes guard: if project is not Rust, only report. |
| `java-code-rules.mdc` | Java only | SLF4J logging (with isXxxEnabled() checks), Spring Boot, structure. `globs: ["**/*.java", "**/pom.xml", "**/build.gradle"]`. Includes guard: if project is not Java, only report. |
| `drawio-rules.mdc` | Draw.io diagrams | Naming, colors, layout, flow lines, version workflow, CHANGELOG. `globs: ["**/*.drawio", "**/*.drawio.svg", "**/docs/**/diagrams/**"]`. |

## Adding or updating a rule

1. **Decide placement**
   - **Convention shared by all Go/communicator repos** → agentic-workspace `.cursor/rules/` (new or existing .mdc).
   - **Single-repo or language-specific** → either here with globs (e.g. Go, Rust) or in that repo’s `.cursor/rules/`.

2. **Format**
   - Use YAML frontmatter: `description`, and `globs` when the rule is file-specific.
   - Example:
     ```yaml
     ---
     description: Short description. Only active for X projects.
     globs: ["**/*.go"]
     ---
     ```
   - For language-specific rules that must not run in other languages, add an explicit instruction in the body (e.g. “If the project is not using RUST, do not run these rules; only report.”).

3. **After changing rules**
   - If you changed shared conventions, consider a brief update to `rules.md` so the human-readable summary stays in sync. Do not duplicate full rule text in `rules.md`.

## Commands and docs

- **AGENTS.md** — When to use agentic-workspace agent; what it provides. Update if you add a new rule category or agent.
- **.cursor/commands/mr.md** — Command for creating MRs; usable from any repo via `@agentic-workspace/.cursor/commands/mr.md`.
- **README.md** — Explains folder purpose and usage; update if the rule layout or usage changes.

## Quick checklist for new rules

- [ ] Correct location (agentic-workspace vs repo).
- [ ] Frontmatter has `description`; add `globs` if file-specific.
- [ ] Language guard in body if rule must not run for other languages.
- [ ] `rules.md` / AGENTS.md updated if the change affects shared conventions or agent scope.
