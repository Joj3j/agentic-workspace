---
name: confluence-page
description: Read or write (create) a Confluence page using the REST API scripts. Use when the user asks to read, fetch, summarize, create, or publish a Confluence page, or gives a Confluence URL. For write/create, asks for the parent page title if not provided.
---

# Confluence page (read / write)

Use this skill when the user asks to **read** or **write** a Confluence page. The Nokia NSP Confluence MCP may be blocked by admin; these scripts use the Confluence REST API directly.

## Prerequisites — environment setup

Before running either script, the Confluence env vars must be set **in the same terminal**:

```bash
cd <workspace-settings>/.cursor/scripts/confluence && source confluence_env.sh
```

This sources `confluence_env.local` (gitignored) which must export:

| Variable | Purpose |
|----------|---------|
| `CONFLUENCE_BASE_URL` | e.g. `https://confluence.ext.net.nokia.com` |
| `CONFLUENCE_USERNAME` | Confluence username |
| `CONFLUENCE_API_TOKEN` | PAT (or `CONFLUENCE_CURSOR_TOKEN` / `CONFLUENCE_PASSWORD` as aliases) |

If `confluence_env.local` does not exist, tell the user:

> Copy `confluence_env.local.example` → `confluence_env.local` (both in `.cursor/scripts/confluence/`), set your values, then `source confluence_env.sh`.

## Scripts

| Script | Location |
|--------|----------|
| Read | `workspace-settings/.cursor/scripts/confluence/confluence_read_page.py` |
| Create | `workspace-settings/.cursor/scripts/confluence/confluence_create_page.py` |
| Env loader | `workspace-settings/.cursor/scripts/confluence/confluence_env.sh` |
| Secrets template | `workspace-settings/.cursor/scripts/confluence/confluence_env.local.example` → copy to `confluence_env.local` (gitignored) |

---

## Per-repo file layout

All generated Confluence HTML and diagrams live under the **target repo's own `docs/` directory**:

```
<repo>/docs/
  confluence/
    body.html                            # Confluence page body (HTML)
    diagrams/                            # draw.io files for Confluence upload
      <repo>_components_v1.drawio
      <repo>_data_flow_v1.drawio
  actual/                                # Detailed local HDD (markdown)
    System_Design_HighLevel.md
```

| Artifact | Location | Notes |
|----------|----------|-------|
| **Confluence body** | `<repo>/docs/confluence/body.html` | Single HTML file with all HLD sections (H1–H12). |
| **Draw.io diagrams** | `<repo>/docs/confluence/diagrams/` | Component, data flow, and other draw.io files. Upload via Confluence UI after page creation. |
| **Local HDD** | `<repo>/docs/actual/System_Design_HighLevel.md` | Detailed markdown (Mermaid diagrams, API tables, samples). |

When **generating** a Confluence body (e.g. from an arch doc skill or user request):
1. Create/update `<repo>/docs/confluence/body.html`.
2. Place draw.io diagrams in `<repo>/docs/confluence/diagrams/`.
3. Reference diagrams from the HTML body with relative links and Confluence upload instructions.

**Do not** store generated HTML or diagrams in `workspace-settings/docs/`.

---

## Read a page

### By title and space

```bash
python3 confluence_read_page.py --title "Page Title" --space-key NSPArchEvo
```

- `--space-key` defaults to `NSPArchEvo`.
- From a URL like `.../display/NSPArchEvo/MDC+Wrapper+Server`, decode `+` → space for `--title`, use path segment for `--space-key`.

### By page ID

```bash
python3 confluence_read_page.py --page-id 123456789
```

### Output format

| Flag | Output |
|------|--------|
| `--format text` (default) | Readable plain text (HTML stripped) |
| `--format html` | Raw HTML body |
| `--format json` | Full API response |

### Agent steps (read)

1. Source env: `cd <workspace-settings>/.cursor/scripts/confluence && source confluence_env.sh`
2. Run the read script with the appropriate flags.
3. Use stdout as the page content. If exit code is non-zero or stderr has errors, report the error.

---

## Write (create) a page

### Required information

Before creating a page, you **must** have:

| Field | How to get it |
|-------|---------------|
| **Page title** | User provides it, or derive from context. |
| **Parent page** | User provides `--parent-id` or `--parent-title`. **If neither is available, ask the user:** _"Under which Confluence parent page should this be created? Provide a parent page title (and space key) or a parent page ID."_ |
| **Space key** | Defaults to `NSPArchEvo`; ask if different space is needed. |
| **Body** | HTML string (`--body`) or HTML file (`--body-file`). For markdown content, convert to HTML first (e.g. `pandoc -f markdown -t html`). |

### By parent title

```bash
python3 confluence_create_page.py \
  --parent-title "Parent Page Title" \
  --space-key NSPArchEvo \
  --title "New Page Title" \
  --body "<p>Content here.</p>"
```

### By parent ID

```bash
python3 confluence_create_page.py \
  --parent-id 2069174542 \
  --title "New Page Title" \
  --body "<p>Content here.</p>"
```

### Using a body file (preferred for arch pages)

```bash
python3 confluence_create_page.py \
  --parent-id 2069174542 \
  --space-key NSPArchEvo \
  --title "Device Registry Arch" \
  --body-file <repo>/docs/confluence/body.html
```

### Agent steps (write)

1. Source env: `cd <workspace-settings>/.cursor/scripts/confluence && source confluence_env.sh`
2. Determine the **parent page**:
   - If the user gave a parent page title or ID → use it.
   - If the context implies a known parent (e.g. arch pages use parent ID `2069174542`) → use it.
   - **Otherwise, ask the user**: _"Under which Confluence parent page should this new page be created? Please provide a parent page title (and space key if not NSPArchEvo) or a page ID."_
3. Determine the **page title**: ask the user if not obvious from context.
4. Prepare the body content as HTML:
   - If an existing `<repo>/docs/confluence/body.html` is available → use `--body-file`.
   - If generating new content → write it to `<repo>/docs/confluence/body.html` first, then use `--body-file`.
   - If the source is markdown → convert to HTML (e.g. `pandoc -f markdown -t html`) and save to `<repo>/docs/confluence/body.html`.
5. Run the create script. On success, report the page URL from stdout. On failure, report the error.
6. If diagrams exist in `<repo>/docs/confluence/diagrams/`, remind the user to upload them via Confluence UI (Insert → draw.io).

---

## Parsing Confluence URLs

When the user provides a URL, extract the parameters:

| URL pattern | Extract |
|-------------|---------|
| `.../display/<SpaceKey>/<Page+Title>` | `--space-key <SpaceKey>` and `--title "<Page Title>"` (decode `+` → space) |
| `.../pages/viewpage.action?pageId=<ID>` | `--page-id <ID>` |

## Common parent pages (NSPArchEvo)

| Name | ID | Use for |
|------|----|---------|
| NSP Architecture Evolution (root) | — | Top-level; avoid creating directly here |
| Architecture pages parent | `2069174542` | New architecture / HLD pages |

## Existing arch pages by repo

| Repo | Confluence body | Diagrams |
|------|----------------|----------|
| **device-registry** | `device-registry/docs/confluence/body.html` | `device-registry/docs/confluence/diagrams/` |
| **comm-layer-server** | `comm-layer-server/docs/confluence/body.html` | `comm-layer-server/docs/confluence/diagrams/` |

## Error handling

- **Env not set**: script prints `Error: set CONFLUENCE_*` — tell the user to set up `confluence_env.local`.
- **Page not found** (read): check title spelling and space key; try `--format json` for debugging.
- **Create failed (4xx)**: usually title conflict (page already exists) or missing parent — report the status and message.

## Examples

| User says | Agent does |
|-----------|------------|
| "Read the MDC Wrapper Server page" | `confluence_read_page.py --title "MDC Wrapper Server" --space-key NSPArchEvo` |
| "Show me https://confluence.ext.net.nokia.com/display/NSPArchEvo/Some+Page" | `confluence_read_page.py --title "Some Page" --space-key NSPArchEvo` |
| "Get page 987654321 as HTML" | `confluence_read_page.py --page-id 987654321 --format html` |
| "Create a page called 'My Service' under MDC Wrapper Server" | `confluence_create_page.py --parent-title "MDC Wrapper Server" --space-key NSPArchEvo --title "My Service" --body "..."` |
| "Publish device-registry arch to Confluence" | `confluence_create_page.py --parent-id 2069174542 --title "Device Registry Arch" --body-file device-registry/docs/confluence/body.html` |
| "Publish this doc to Confluence" (no parent given) | **Ask**: "Under which parent page?" → then run create script with `--body-file <repo>/docs/confluence/body.html` |
