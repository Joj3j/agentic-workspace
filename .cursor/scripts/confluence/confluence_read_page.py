#!/usr/bin/env python3
"""
Read a Confluence page via REST API (no MCP required).

Use when the Atlassian MCP is blocked by admin. Run locally or via an agent.

Usage:
  export CONFLUENCE_BASE_URL="https://confluence.ext.net.nokia.com"
  export CONFLUENCE_USERNAME="jojijose"
  export CONFLUENCE_API_TOKEN="your-token"

  # By title and space
  python3 confluence_read_page.py --title "MDC Wrapper Server" --space-key NSPArchEvo

  # By page ID
  python3 confluence_read_page.py --page-id 123456789

  # Output format: --format text (default, strip HTML), --format html, or --format json (full API response)
"""

import argparse
import json
import os
import re
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
) -> tuple[int, dict]:
    url = urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    print(f"confluence_read_page: GET {url}", file=sys.stderr)
    req = urllib.request.Request(url, method="GET")
    req.add_header("Accept", "application/json")
    # Confluence PAT: use Bearer token (not Basic)
    req.add_header("Authorization", f"Bearer {token}")
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


def get_page(
    base_url: str,
    username: str,
    token: str,
    page_id: str | None = None,
    title: str | None = None,
    space_key: str | None = None,
    expand: str = "body.storage,body.view,version",
) -> dict | None:
    if page_id:
        path = f"/rest/api/content/{page_id}?expand={urllib.parse.quote(expand)}"
    elif title and space_key:
        path = (
            "/rest/api/content"
            f"?spaceKey={urllib.parse.quote(space_key)}"
            f"&title={urllib.parse.quote(title)}"
            f"&expand={urllib.parse.quote(expand)}"
        )
    else:
        print("Error: provide --page-id or both --title and --space-key", file=sys.stderr)
        return None
    code, data = make_request(base_url, username, token, path)
    if code != 200:
        print(f"Request failed: {code} {data}", file=sys.stderr)
        return None
    results = data.get("results")
    if results:
        return results[0]
    if data.get("id"):
        return data
    print(f"Page not found: {data}", file=sys.stderr)
    return None


def html_to_plain(html: str) -> str:
    """Rough strip of HTML for readable text."""
    if not html:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|h[1-6]|li|tr)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def main():
    parser = argparse.ArgumentParser(description="Read a Confluence page via REST API")
    parser.add_argument("--page-id", help="Page ID (from URL or API)")
    parser.add_argument("--title", help="Page title (use with --space-key)")
    parser.add_argument("--space-key", default="NSPArchEvo", help="Space key (e.g. NSPArchEvo)")
    parser.add_argument(
        "--format",
        choices=("text", "html", "json"),
        default="text",
        help="Output: text (plain), html (body.view), or json (full response)",
    )
    args = parser.parse_args()

    if not args.page_id and not args.title:
        parser.error("provide --page-id or --title (and optionally --space-key)")
    if args.page_id and args.title:
        parser.error("provide either --page-id or --title, not both")

    base_url = get_env("CONFLUENCE_BASE_URL").rstrip("/")
    username = get_env("CONFLUENCE_USERNAME")
    token = get_env("CONFLUENCE_API_TOKEN")
    if not token and os.environ.get("CONFLUENCE_PASSWORD"):
        token = os.environ.get("CONFLUENCE_PASSWORD", "").strip()

    page = get_page(
        base_url,
        username,
        token,
        page_id=args.page_id,
        title=args.title,
        space_key=args.space_key,
    )
    if not page:
        sys.exit(1)

    if args.format == "json":
        print(json.dumps(page, indent=2))
        sys.exit(0)

    body_view = (page.get("body") or {}).get("view") or {}
    body_storage = (page.get("body") or {}).get("storage") or {}
    html = body_view.get("value") or body_storage.get("value") or ""

    if args.format == "html":
        print(html)
    else:
        print(f"# {page.get('title', '')}\n")
        print(html_to_plain(html))
    sys.exit(0)


if __name__ == "__main__":
    main()
