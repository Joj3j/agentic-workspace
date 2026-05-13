#!/usr/bin/env python3
"""
Create a Confluence page via REST API (no MCP required).

Use when the Atlassian MCP is blocked by admin. Run locally with your credentials.

Usage:
  export CONFLUENCE_BASE_URL="https://confluence.ext.net.nokia.com"
  export CONFLUENCE_USERNAME="jojijose"
  export CONFLUENCE_API_TOKEN="your-token"

  # Create a child page under "MDC Wrapper Server" in space NSPArchEvo
  python3 confluence_create_page.py --parent-title "MDC Wrapper Server" --space-key NSPArchEvo --title "My New Arch Page" --body "<p>Content here.</p>"

  # Or pass parent page ID directly (skip lookup)
  python3 confluence_create_page.py --parent-id 123456789 --title "My New Arch Page" --body "<p>Content here.</p>"
"""

import argparse
import os
import sys
import urllib.parse
import urllib.request


def get_env(name: str, required: bool = True, strip: bool = True) -> str:
    val = os.environ.get(name)
    if required and not val:
        print(f"Error: set {name}", file=sys.stderr)
        sys.exit(1)
    out = val or ""
    return out.strip() if strip else out


def make_request(
    base_url: str,
    username: str,
    token: str,
    path: str,
    method: str = "GET",
    data: bytes | None = None,
) -> tuple[int, dict]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    # Confluence PAT: use Bearer token (not Basic)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.data = data
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            import json
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            import json
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"message": body}
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def find_page_id_by_title(base_url: str, username: str, token: str, space_key: str, title: str) -> str | None:
    # CQL search for page in space by title
    path = f"/rest/api/content?spaceKey={urllib.parse.quote(space_key)}&title={urllib.parse.quote(title)}&expand=version"
    code, data = make_request(base_url, username, token, path)
    if code != 200:
        print(f"Lookup failed: {code} {data}", file=sys.stderr)
        return None
    results = data.get("results", [])
    if not results:
        print(f"No page found with title '{title}' in space {space_key}", file=sys.stderr)
        return None
    return results[0].get("id")


def create_page(
    base_url: str,
    username: str,
    token: str,
    space_key: str,
    parent_id: str,
    title: str,
    body_html: str,
) -> bool:
    import json
    payload = {
        "type": "page",
        "title": title,
        "space": {"key": space_key},
        "ancestors": [{"id": parent_id}],
        "body": {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        },
    }
    path = "/rest/api/content"
    code, data = make_request(base_url, username, token, path, method="POST", data=json.dumps(payload).encode())
    if code not in (200, 201):
        print(f"Create failed: {code} {data}", file=sys.stderr)
        return False
    page_id = data.get("id")
    link = data.get("_links", {}).get("webui", "")
    print(f"Created page id={page_id}")
    print(f"URL: {urllib.parse.urljoin(base_url.rstrip('/') + '/', link)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Create a Confluence page via REST API")
    parser.add_argument("--parent-id", help="Parent page ID (optional if --parent-title and --space-key are set)")
    parser.add_argument("--parent-title", default="MDC Wrapper Server", help="Parent page title for lookup")
    parser.add_argument("--space-key", default="NSPArchEvo", help="Space key (e.g. NSPArchEvo)")
    parser.add_argument("--title", required=True, help="Title of the new page")
    parser.add_argument("--body", default="<p>New architecture page.</p>", help="HTML body for the page")
    parser.add_argument("--body-file", help="Read body from file (HTML); overrides --body")
    args = parser.parse_args()

    base_url = get_env("CONFLUENCE_BASE_URL").rstrip("/")
    username = get_env("CONFLUENCE_USERNAME")
    token = get_env("CONFLUENCE_API_TOKEN")
    if not token and os.environ.get("CONFLUENCE_PASSWORD"):
        token = os.environ.get("CONFLUENCE_PASSWORD", "").strip()

    body = args.body
    if args.body_file:
        with open(args.body_file, "r") as f:
            body = f.read()

    parent_id = args.parent_id
    if not parent_id:
        parent_id = find_page_id_by_title(base_url, username, token, args.space_key, args.parent_title)
        if not parent_id:
            sys.exit(1)
        print(f"Using parent page id: {parent_id}")

    if create_page(base_url, username, token, args.space_key, parent_id, args.title, body):
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
