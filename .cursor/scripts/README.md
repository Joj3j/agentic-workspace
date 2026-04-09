# Scripts (under .cursor)

Scripts used with the workspace: Confluence, etc. Skills live in `.cursor/skills/`.

## Confluence: set env (run first)

Invoke this **first** so Confluence read/create scripts have credentials. **Source** it in your shell (same shell you use for the Python scripts):

```bash
cd agentic-workspace/.cursor/scripts
source confluence_env.sh
```

First-time setup: copy the example file and set your values (the local file is gitignored):

```bash
cp confluence_env.local.example confluence_env.local
# Edit confluence_env.local: set CONFLUENCE_BASE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN
```

Then in the **same** shell you can run `confluence_read_page.py` or `confluence_create_page.py` without exporting vars each time.

## Confluence: read page (no MCP)

**Agent command:** Use the Cursor command **Confluence: read page** (`.cursor/commands/confluence-read.md`) so the agent knows how to run this script.

Read a page by title + space or by page ID. Set env first with `source confluence_env.sh` (see above), or export the Confluence vars manually.

```bash
# By title and space (default space NSPArchEvo)
python3 confluence_read_page.py --title "MDC Wrapper Server" --space-key NSPArchEvo

# By page ID
python3 confluence_read_page.py --page-id 123456789

# Output: --format text (default), --format html, or --format json
python3 confluence_read_page.py --title "Some Page" --space-key NSPArchEvo --format html
```

## Confluence: create page (no MCP)

When the Nokia NSP Confluence MCP is **blocked by admin**, use the Confluence REST API script to create pages from the terminal or from an agent (agent runs the script with your env vars).

**Setup (once):** Run `source confluence_env.sh` first (see “Confluence: set env” above), or export the three Confluence vars manually.

**Create a new arch page under [MDC Wrapper Server](https://confluence.ext.net.nokia.com/display/NSPArchEvo/MDC+Wrapper+Server):**

```bash
cd agentic-workspace/.cursor/scripts
python3 confluence_create_page.py \
  --parent-title "MDC Wrapper Server" \
  --space-key NSPArchEvo \
  --title "Your New Page Title" \
  --body "<p>Intro paragraph.</p><h2>Section</h2><p>More content.</p>"
```

**Use a file for the body (e.g. Markdown/HTML):**

```bash
python3 confluence_create_page.py \
  --parent-title "MDC Wrapper Server" \
  --space-key NSPArchEvo \
  --title "Your New Page Title" \
  --body-file ./my_page.html
```

Confluence expects **HTML** in `--body` / `--body-file`. For Markdown, convert to HTML first (e.g. `pandoc -f markdown -t html`) or paste HTML.

**If you already have the parent page ID** (from the page URL or API):

```bash
python3 confluence_create_page.py --parent-id 123456789 --title "Your New Page Title" --body "<p>Content.</p>"
```
