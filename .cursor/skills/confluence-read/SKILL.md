---
name: confluence-read
description: Read a Confluence page via the REST API script. Use when the user asks to read, fetch, summarize, or show a Confluence page, or gives a Confluence URL or page ID for read-only access. Same environment as confluence-page; does not create pages.
---

# Confluence read (REST API)

Use this skill when the user needs to **read** Confluence content only (summarize, quote, diff against local HTML, verify published text). The Nokia NSP Confluence MCP may be blocked by admin; this uses the Confluence REST API directly.

**Create / publish pages:** use **`agentic-workspace/.cursor/skills/confluence-page/SKILL.md`** (`confluence_create_page.py`).

---

## Prerequisites — environment setup (same as confluence-page)

Run scripts only after sourcing env vars **in the same terminal** (use the **IDE terminal** so credentials match your shell; avoid sandbox if env would be missing):

```bash
cd agentic-workspace/.cursor/scripts/confluence && source confluence_env.sh
```

This sources `confluence_env.local` (gitignored), which must export:

| Variable | Purpose |
|----------|---------|
| `CONFLUENCE_BASE_URL` | e.g. `https://confluence.ext.net.nokia.com` |
| `CONFLUENCE_USERNAME` | Confluence username |
| `CONFLUENCE_API_TOKEN` | PAT (aliases supported by `confluence_env.sh`: `CONFLUENCE_CURSOR_TOKEN`, `CONFLUENCE_PASSWORD`) |

If `confluence_env.local` does not exist, tell the user:

> Copy `confluence_env.local.example` → `confluence_env.local` (both under `agentic-workspace/.cursor/scripts/confluence/`), set the variables, then `source confluence_env.sh`.

These are the **same** variables and paths as the **confluence-page** skill.

---

## Script

| Script | Path |
|--------|------|
| Read | `agentic-workspace/.cursor/scripts/confluence/confluence_read_page.py` |
| Env loader | `agentic-workspace/.cursor/scripts/confluence/confluence_env.sh` |
| Secrets template | `agentic-workspace/.cursor/scripts/confluence/confluence_env.local.example` → `confluence_env.local` |

Always `cd` to `confluence/` (or use absolute paths) so `source confluence_env.sh` and `python3 confluence_read_page.py` run from the directory that contains both files.

---

## Read a page

### By title and space

```bash
cd agentic-workspace/.cursor/scripts/confluence && source confluence_env.sh
python3 confluence_read_page.py --title "Page Title" --space-key NSPArchEvo
```

- `--space-key` defaults to `NSPArchEvo` if omitted (check script help).
- From a URL `.../display/NSPArchEvo/MDC+Wrapper+Server`: `--space-key NSPArchEvo`, `--title "MDC Wrapper Server"` (decode `+` as space).

### By page ID

```bash
cd agentic-workspace/.cursor/scripts/confluence && source confluence_env.sh
python3 confluence_read_page.py --page-id 123456789
```

From a URL `.../pages/viewpage.action?pageId=<ID>`: use `--page-id <ID>`.

### Output format

| Flag | Output |
|------|--------|
| `--format text` (default) | Readable plain text (HTML stripped) |
| `--format html` | Raw storage-format HTML body |
| `--format json` | Full API response (debugging) |

### Agent steps

1. `cd agentic-workspace/.cursor/scripts/confluence && source confluence_env.sh`
2. Run `confluence_read_page.py` with `--title` / `--space-key` or `--page-id`, and optional `--format`.
3. Treat **stdout** as the page content. If exit code is non-zero or stderr shows errors, report the error and do not treat stdout as authoritative.

---

## Error handling

- **Env not set**: script may print `Error: set CONFLUENCE_*` — user must create `confluence_env.local` from the example (same as confluence-page).
- **Page not found**: verify title spelling, space key, and `--format json` for API details.

---

## Examples

| User says | Agent does |
|-----------|------------|
| "Read the MDC Wrapper Server page" | After `source confluence_env.sh`: `python3 confluence_read_page.py --title "MDC Wrapper Server" --space-key NSPArchEvo` |
| "Summarize https://confluence.../display/NSPArchEvo/Some+Page" | Parse URL → `--title "Some Page" --space-key NSPArchEvo` |
| "Raw HTML for page ID 987654321" | `python3 confluence_read_page.py --page-id 987654321 --format html` |
