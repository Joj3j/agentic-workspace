#!/usr/bin/env python3
"""
Update an existing Confluence page's body via REST API (no MCP required).

Use when the Atlassian MCP is blocked by admin. Run locally with your credentials.

Usage:
  export CONFLUENCE_BASE_URL="https://confluence.ext.net.nokia.com"
  export CONFLUENCE_USERNAME="jojijose"
  export CONFLUENCE_API_TOKEN="your-token"

  # By page ID
  python3 confluence_update_page.py --page-id 123456789 --body-file body.html

  # By title and space (lookup id + current version automatically)
  python3 confluence_update_page.py --title "My Page" --space-key NSPArchEvo --body-file body.html
"""

import argparse
import json
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
    token: str,
    path: str,
    method: str = "GET",
    data: bytes | None = None,
) -> tuple[int, dict]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.data = data
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"message": body}
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        sys.exit(1)


def find_page(base_url: str, token: str, page_id: str | None, title: str | None, space_key: str | None) -> dict | None:
    if page_id:
        path = f"/rest/api/content/{page_id}?expand=version,body.storage"
    else:
        path = (
            "/rest/api/content"
            f"?spaceKey={urllib.parse.quote(space_key)}"
            f"&title={urllib.parse.quote(title)}"
            "&expand=version,body.storage"
        )
    code, data = make_request(base_url, token, path)
    if code != 200:
        print(f"Lookup failed: {code} {data}", file=sys.stderr)
        return None
    results = data.get("results")
    if results:
        return results[0]
    if data.get("id"):
        return data
    print(f"Page not found: {data}", file=sys.stderr)
    return None


def update_page(base_url: str, token: str, page_id: str, title: str, new_version: int, body_html: str) -> bool:
    payload = {
        "id": page_id,
        "type": "page",
        "title": title,
        "version": {"number": new_version},
        "body": {
            "storage": {
                "value": body_html,
                "representation": "storage",
            }
        },
    }
    path = f"/rest/api/content/{page_id}"
    code, data = make_request(base_url, token, path, method="PUT", data=json.dumps(payload).encode())
    if code not in (200, 201):
        print(f"Update failed: {code} {data}", file=sys.stderr)
        return False
    link = data.get("_links", {}).get("webui", "")
    print(f"Updated page id={page_id} version={data.get('version', {}).get('number')}")
    print(f"URL: {urllib.parse.urljoin(base_url.rstrip('/') + '/', link)}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Update a Confluence page body via REST API")
    parser.add_argument("--page-id", help="Page ID (skips title lookup)")
    parser.add_argument("--title", help="Page title (use with --space-key)")
    parser.add_argument("--space-key", default="NSPArchEvo", help="Space key (e.g. NSPArchEvo)")
    parser.add_argument("--new-title", help="Optional new title (defaults to unchanged)")
    parser.add_argument("--body", help="HTML body for the page (storage format)")
    parser.add_argument("--body-file", help="Read body from file (HTML); overrides --body")
    args = parser.parse_args()

    if not args.page_id and not args.title:
        parser.error("provide --page-id or --title (and optionally --space-key)")

    base_url = get_env("CONFLUENCE_BASE_URL").rstrip("/")
    get_env("CONFLUENCE_USERNAME")  # kept for parity with other scripts / possible future basic auth
    token = get_env("CONFLUENCE_API_TOKEN")
    if not token and os.environ.get("CONFLUENCE_PASSWORD"):
        token = os.environ.get("CONFLUENCE_PASSWORD", "").strip()

    body = args.body
    if args.body_file:
        with open(args.body_file, "r") as f:
            body = f.read()
    if not body:
        parser.error("provide --body or --body-file")

    page = find_page(base_url, token, args.page_id, args.title, args.space_key)
    if not page:
        sys.exit(1)

    page_id = page.get("id")
    current_version = page.get("version", {}).get("number", 0)
    title = args.new_title or page.get("title")

    if update_page(base_url, token, page_id, title, current_version + 1, body):
        sys.exit(0)
    sys.exit(1)


if __name__ == "__main__":
    main()
