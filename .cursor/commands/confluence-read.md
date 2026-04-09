# Confluence: read page (agent command)

Use this when you need to **read** a Confluence page (e.g. to answer questions, summarize, or use its content). The Nokia NSP Confluence MCP may be blocked by admin; this command uses the Confluence REST API script instead.

## When to use

- User asks to read, show, or summarize a Confluence page.
- User gives a Confluence URL (e.g. `https://confluence.ext.net.nokia.com/display/NSPArchEvo/MDC+Wrapper+Server`) and you need the page content.
- You need up-to-date content from a known page title and space.

## How to run (agent)

1. **Environment**  
   The read script needs `CONFLUENCE_BASE_URL`, `CONFLUENCE_USERNAME`, and `CONFLUENCE_API_TOKEN` set in the shell. The user can invoke the env script **first** in the same terminal:
   ```bash
   cd <agentic-workspace>/.cursor/scripts && source confluence_env.sh
   ```
   That sources `confluence_env.local` . If the user has not set up the env script, they must export the three vars manually in that shell.

2. **Run the read script** from the agentic-workspace repo (in the same shell that has the env vars):
   - Script path: `agentic-workspace/.cursor/scripts/confluence_read_page.py`
   - Use the **existing IDE terminal** (same as for git). Do not run in a sandbox if that would miss the user's env vars.

3. **By page title and space** (typical when user shares a Confluence URL):
   ```bash
   cd <agentic-workspace>/.cursor/scripts
   python3 confluence_read_page.py --title "MDC Wrapper Server" --space-key NSPArchEvo
   ```
   - From a URL like `.../display/NSPArchEvo/MDC+Wrapper+Server`, use:
     - `--space-key NSPArchEvo` (from `display/NSPArchEvo/...`)
     - `--title "MDC Wrapper Server"` (from `.../MDC+Wrapper+Server`; decode + as space).

4. **By page ID** (if the user or a previous call gives a page ID):
   ```bash
   python3 confluence_read_page.py --page-id 123456789
   ```

5. **Output format** (optional):
   - Default: `--format text` (readable plain text for the user/agent).
   - `--format html`: raw HTML body.
   - `--format json`: full API response (for parsing or debugging).

6. **Use the output**  
   Use the script’s stdout as the page content: summarize it, quote it, or base your answer on it. If the script exits non-zero or prints to stderr, report the error and do not treat the output as valid content.

## Examples (for the agent)

- User: “What does the MDC Wrapper Server page say?”  
  → Run: `confluence_read_page.py --title "MDC Wrapper Server" --space-key NSPArchEvo`  
  → Use the printed content to answer.

- User: “Read https://confluence.ext.net.nokia.com/display/NSPArchEvo/Some+Page”  
  → Run: `confluence_read_page.py --title "Some Page" --space-key NSPArchEvo`  
  → Use the printed content to answer.

- User: “Get the raw HTML of page ID 987654321”  
  → Run: `confluence_read_page.py --page-id 987654321 --format html`

## Notes

- If env vars are not set, the script will fail; ask the user to set `CONFLUENCE_BASE_URL`, `CONFLUENCE_USERNAME`, and `CONFLUENCE_API_TOKEN` (e.g. in their shell or in Cursor’s environment).
- Script location: `agentic-workspace/.cursor/scripts/confluence_read_page.py` (agentic-workspace repo is in the workspace).
