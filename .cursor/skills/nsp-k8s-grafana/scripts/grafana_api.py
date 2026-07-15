#!/usr/bin/env python3
"""
NSP Grafana API client — works with Grafana behind the NSP gateway at /grafana/.

Reads configuration from environment variables (source nsp_grafana_env.sh first):
  NSP_GATEWAY       - Gateway host (e.g. 100.127.233.195)
  NSP_USER          - Username (default: admin)
  NSP_PASSWORD      - Password
  NSP_HTTPS_SCHEME  - https (default) or http
  NSP_VERIFY_TLS    - 0 = skip TLS verify (default), 1 = verify
  GRAFANA_SUBPATH   - Subpath (default: /grafana)
  GRAFANA_API_KEY   - Optional bearer token (overrides user/pass, skips OAuth)
  GRAFANA_URL       - Full URL override (built from above if not set)

Authentication: Keycloak OAuth (NSP standard) with cookie session. Falls back to
Basic Auth if OAuth endpoint is unavailable. Set GRAFANA_API_KEY to skip OAuth.

Commands:
  health                                    Check Grafana reachability
  datasources list                          List Prometheus and other datasources
  dashboards list                           List all dashboards
  dashboards search <keyword>               Search dashboards by name
  dashboards get <uid>                      Show dashboard panels and metadata
  dashboards export <uid> [-o FILE]         Download dashboard JSON to file
  dashboards import <file> [--overwrite]    Upload dashboard JSON
  dashboards url <grafana-url> [-o FILE]    Extract UID from URL and export
  dashboards diff <uid> <file>              Compare live vs local dashboard JSON
  query <promql>                            Instant PromQL query
  query-range <promql> [--start 1h]         Range PromQL query
  panels list <dashboard-uid>               List all panels with IDs
  panels render <dashboard-uid> <panel-id>  Render panel to PNG
  test-counters <file-or-uid>               Validate all PromQL counters in a dashboard
  open <uid>                                Print browser and JSON editor URLs
"""

import argparse
import base64
import http.cookiejar
import json
import os
import re
import ssl
import sys
import time
from datetime import datetime
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPSHandler


# ── Configuration ─────────────────────────────────────────────────────────────

def _env(name, default=None, required=False):
    val = os.environ.get(name, default)
    if required and not val:
        print(f"ERROR: {name} is not set. Run: source scripts/nsp_grafana_env.sh", file=sys.stderr)
        sys.exit(1)
    return val


def _grafana_base():
    explicit = os.environ.get("GRAFANA_URL")
    if explicit:
        return explicit.rstrip("/")
    gw = _env("NSP_GATEWAY", required=True)
    scheme = _env("NSP_HTTPS_SCHEME", "https")
    subpath = _env("GRAFANA_SUBPATH", "/grafana")
    return f"{scheme}://{gw}{subpath}"


def _host_base():
    explicit = os.environ.get("GRAFANA_URL")
    if explicit:
        from urllib.parse import urlparse
        p = urlparse(explicit)
        return f"{p.scheme}://{p.netloc}"
    gw = _env("NSP_GATEWAY", required=True)
    scheme = _env("NSP_HTTPS_SCHEME", "https")
    return f"{scheme}://{gw}"


def _ssl_ctx():
    ctx = ssl.create_default_context()
    if _env("NSP_VERIFY_TLS", "0") == "0":
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _basic_auth_header():
    user = _env("NSP_USER", "admin")
    pw = _env("NSP_PASSWORD", required=True)
    cred = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return f"Basic {cred}"


# ── Keycloak OAuth session ────────────────────────────────────────────────────

class _FormActionParser(HTMLParser):
    """Extract the action URL from the first HTML form tag."""
    def __init__(self):
        super().__init__()
        self.action = None

    def handle_starttag(self, tag, attrs):
        if tag == "form" and self.action is None:
            self.action = dict(attrs).get("action", "")


_session = {
    "opener": None,       # urllib opener with cookie jar
    "authenticated": False,
    "use_basic_auth": False,  # True when Keycloak is unavailable
}


def _get_opener():
    if _session["opener"] is None:
        jar = http.cookiejar.CookieJar()
        _session["opener"] = build_opener(
            HTTPCookieProcessor(jar),
            HTTPSHandler(context=_ssl_ctx()),
        )
    return _session["opener"]


def _login_keycloak():
    """Authenticate via NSP Keycloak OAuth — follows the browser redirect flow."""
    base = _grafana_base()
    host = _host_base()
    opener = _get_opener()
    user = _env("NSP_USER", "admin")
    pw = _env("NSP_PASSWORD", required=True)

    # Step 1: initiate OAuth → Grafana redirects to Keycloak
    r1 = opener.open(f"{base}/login/generic_oauth", timeout=30)
    keycloak_html = r1.read().decode("utf-8", errors="replace")
    keycloak_url = r1.geturl()

    # Step 2: parse Keycloak login form action
    parser = _FormActionParser()
    parser.feed(keycloak_html)
    if not parser.action:
        raise RuntimeError("Keycloak login form not found — check credentials or OAuth config")
    action = parser.action.replace("&amp;", "&")
    if action.startswith("/"):
        from urllib.parse import urlparse
        u = urlparse(keycloak_url)
        action = f"{u.scheme}://{u.netloc}{action}"

    # Step 3: submit credentials
    body = urlencode({"username": user, "password": pw}).encode()
    req = Request(action, data=body,
                  headers={"Content-Type": "application/x-www-form-urlencoded"})
    r3 = opener.open(req, timeout=30)
    r3.read()

    _session["authenticated"] = True
    print("  Authenticated via Keycloak OAuth", file=sys.stderr)


def _ensure_session():
    """Lazy authentication — called before the first API request."""
    if _session["authenticated"] or _session["use_basic_auth"]:
        return
    api_key = _env("GRAFANA_API_KEY")
    if api_key:
        _session["use_basic_auth"] = True  # use header auth with the API key
        return
    try:
        _login_keycloak()
    except Exception as e:
        print(f"  Keycloak OAuth failed ({e}), falling back to Basic Auth", file=sys.stderr)
        _session["use_basic_auth"] = True


def _request_headers(accept="application/json"):
    headers = {"Content-Type": "application/json", "Accept": accept}
    if _session["use_basic_auth"]:
        api_key = _env("GRAFANA_API_KEY")
        headers["Authorization"] = f"Bearer {api_key}" if api_key else _basic_auth_header()
    return headers


# ── Core API call ─────────────────────────────────────────────────────────────

def api(path, method="GET", data=None, accept="application/json", raw=False):
    _ensure_session()
    url = f"{_grafana_base()}{path}"
    body = json.dumps(data).encode() if data else None

    def _do_request():
        req = Request(url, data=body, headers=_request_headers(accept), method=method)
        return _get_opener().open(req, timeout=30)

    try:
        resp = _do_request()
        payload = resp.read()
        if raw:
            return payload
        ct = resp.headers.get("Content-Type", "")
        return json.loads(payload) if "json" in ct else payload
    except HTTPError as e:
        if e.code == 401 and not _session["use_basic_auth"]:
            # Re-authenticate and retry once
            _session["authenticated"] = False
            try:
                _login_keycloak()
                resp = _do_request()
                payload = resp.read()
                if raw:
                    return payload
                ct = resp.headers.get("Content-Type", "")
                return json.loads(payload) if "json" in ct else payload
            except Exception:
                pass
        err = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} {e.reason}\n  URL: {url}\n  Body: {err}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"Connection error: {e.reason}\n  URL: {url}", file=sys.stderr)
        print("  Check NSP_GATEWAY, network, and source nsp_grafana_env.sh", file=sys.stderr)
        sys.exit(1)


# ── Health ────────────────────────────────────────────────────────────────────

def cmd_health(_args):
    base = _grafana_base()
    print(f"Grafana URL: {base}")
    h = api("/api/health")
    print(f"  Database: {h.get('database', '?')}")
    print(f"  Version:  {h.get('version', '?')}")
    print(f"  Commit:   {h.get('commit', '?')}")
    try:
        org = api("/api/org")
        print(f"  Org:      {org.get('name', '?')}")
    except SystemExit:
        pass
    print("Status: OK")


# ── Open URL ──────────────────────────────────────────────────────────────────

def cmd_open(args):
    base = _grafana_base()
    dash_url = (f"{base}/d/{args.uid}"
                f"?orgId=1&from=now-1h&to=now&timezone=browser"
                f"&var-instance=$__all&refresh=10s")
    editor_url = f"{base}/d/{args.uid}?editview=json-model"
    print(f"Dashboard URL:\n  {dash_url}")
    print(f"\nJSON Editor:\n  {editor_url}")


# ── Datasources ───────────────────────────────────────────────────────────────

def cmd_datasources_list(_args):
    ds_list = api("/api/datasources")
    fmt = "{:<6} {:<35} {:<15} {:<50}"
    print(fmt.format("ID", "Name", "Type", "URL"))
    print("-" * 110)
    for ds in sorted(ds_list, key=lambda d: d.get("id", 0)):
        print(fmt.format(ds.get("id", ""), ds.get("name", ""), ds.get("type", ""), ds.get("url", "")))
    return ds_list


# ── Dashboards ────────────────────────────────────────────────────────────────

def _fmt_dash_table(results):
    fmt = "{:<40} {:<20} {:<50}"
    print(fmt.format("UID", "Folder", "Title"))
    print("-" * 110)
    for d in results:
        print(fmt.format(d.get("uid", ""), d.get("folderTitle", "General"), d.get("title", "")))
    print(f"\nTotal: {len(results)}")


def cmd_dashboards_list(_args):
    _fmt_dash_table(api("/api/search?type=dash-db&limit=5000"))


def cmd_dashboards_search(args):
    q = quote(args.keyword)
    results = api(f"/api/search?type=dash-db&query={q}&limit=200")
    if not results:
        print(f"No dashboards matching '{args.keyword}'")
        return
    _fmt_dash_table(results)


def cmd_dashboards_get(args):
    r = api(f"/api/dashboards/uid/{args.uid}")
    meta, dash = r.get("meta", {}), r.get("dashboard", {})
    print(f"Title:    {dash.get('title', 'N/A')}")
    print(f"UID:      {dash.get('uid', 'N/A')}")
    print(f"ID:       {dash.get('id', 'N/A')}")
    print(f"Version:  {dash.get('version', 'N/A')}")
    print(f"Folder:   {meta.get('folderTitle', 'General')}")
    print(f"URL:      {_grafana_base()}{meta.get('url', '')}")
    _print_panels(dash)


def _print_panels(dash, indent=2):
    panels = dash.get("panels", [])
    if not panels:
        return
    print(f"\nPanels ({_count_panels(panels)}):")
    pfmt = "{}{:<6} {:<50} {:<15}"
    for p in panels:
        if p.get("type") == "row":
            print(f"\n{'':>{indent}}--- Row: {p.get('title', '')} ---")
            for sub in p.get("panels", []):
                print(pfmt.format(" " * indent, sub.get("id", ""), sub.get("title", ""), sub.get("type", "")))
        else:
            print(pfmt.format(" " * indent, p.get("id", ""), p.get("title", ""), p.get("type", "")))


def _count_panels(panels):
    n = 0
    for p in panels:
        if p.get("type") == "row":
            n += len(p.get("panels", []))
        else:
            n += 1
    return n


def cmd_dashboards_export(args):
    r = api(f"/api/dashboards/uid/{args.uid}")
    outfile = args.output or f"{args.uid}.json"
    with open(outfile, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    title = r.get("dashboard", {}).get("title", "")
    n = _count_panels(r.get("dashboard", {}).get("panels", []))
    print(f"Exported '{title}' ({n} panels) -> {outfile}")


def cmd_dashboards_url(args):
    """Extract UID from a full Grafana URL and export the dashboard."""
    match = re.search(r'/d/([^/?]+)', args.url)
    if not match:
        print(f"Cannot extract UID from URL: {args.url}", file=sys.stderr)
        sys.exit(1)
    uid = match.group(1)
    print(f"Extracted UID: {uid}")

    class _A:
        pass
    a = _A()
    a.uid = uid
    a.output = getattr(args, "output", None)
    cmd_dashboards_export(a)


def _resolve_datasource_uid_placeholders(raw_text: str) -> str:
    out = raw_text
    for ds in api("/api/datasources"):
        t, uid = ds.get("type"), ds.get("uid")
        if t == "prometheus" and uid and "${DS_PROMETHEUS}" in out:
            out = out.replace("${DS_PROMETHEUS}", uid)
        if t == "loki" and uid and "${DS_LOKI}" in out:
            out = out.replace("${DS_LOKI}", uid)
    return out


def cmd_dashboards_import(args):
    with open(args.file, "r", encoding="utf-8") as f:
        raw_text = f.read()
    if "${DS_" in raw_text:
        print("  Resolving datasource placeholders...", file=sys.stderr)
        raw_text = _resolve_datasource_uid_placeholders(raw_text)
    payload = json.loads(raw_text)
    dashboard = payload.get("dashboard", payload)
    for k in ("id", "__inputs", "__requires", "__elements"):
        dashboard.pop(k, None)
    body = {"dashboard": dashboard, "overwrite": bool(args.overwrite), "folderId": 0}
    r = api("/api/dashboards/db", method="POST", data=body)
    print(f"Imported -> {_grafana_base()}{r.get('url', '')}")
    print(f"  Status:  {r.get('status', '?')}")
    print(f"  UID:     {r.get('uid', '?')}")
    print(f"  Version: {r.get('version', '?')}")


def cmd_dashboards_diff(args):
    live = api(f"/api/dashboards/uid/{args.uid}")
    with open(args.file, "r", encoding="utf-8") as f:
        local = json.load(f)

    live_dash = live.get("dashboard", {})
    local_dash = local.get("dashboard", local)

    live_exprs = _extract_expressions(live_dash)
    local_exprs = _extract_expressions(local_dash)

    live_set = {(t, e) for t, e, _ in live_exprs}
    local_set = {(t, e) for t, e, _ in local_exprs}

    added = local_set - live_set
    removed = live_set - local_set
    unchanged = live_set & local_set

    print(f"Dashboard: {live_dash.get('title', 'N/A')}")
    print(f"Live version:  {live_dash.get('version', '?')}")
    print(f"Local panels:  {_count_panels(local_dash.get('panels', []))}")
    print(f"Live panels:   {_count_panels(live_dash.get('panels', []))}")
    print(f"\nExpressions:  {len(unchanged)} unchanged, +{len(added)} added, -{len(removed)} removed")

    if added:
        print("\n  ADDED (in local, not on server):")
        for title, expr in sorted(added):
            print(f"    [{title}] {expr[:90]}")
    if removed:
        print("\n  REMOVED (on server, not in local):")
        for title, expr in sorted(removed):
            print(f"    [{title}] {expr[:90]}")


# ── Panels ────────────────────────────────────────────────────────────────────

def cmd_panels_list(args):
    r = api(f"/api/dashboards/uid/{args.dashboard_uid}")
    dash = r.get("dashboard", {})
    print(f"Dashboard: {dash.get('title', 'N/A')}\n")
    fmt = "{:<6} {:<50} {:<15} {:<60}"
    print(fmt.format("ID", "Title", "Type", "Expressions"))
    print("-" * 135)
    for p in dash.get("panels", []):
        if p.get("type") == "row":
            print(f"\n--- Row: {p.get('title', '')} ---")
            for sub in p.get("panels", []):
                exprs = [t.get("expr", "")[:55] for t in sub.get("targets", [])]
                print(fmt.format(sub.get("id", ""), sub.get("title", "")[:48], sub.get("type", ""), "; ".join(exprs)[:58]))
        else:
            exprs = [t.get("expr", "")[:55] for t in p.get("targets", [])]
            print(fmt.format(p.get("id", ""), p.get("title", "")[:48], p.get("type", ""), "; ".join(exprs)[:58]))


def cmd_panels_render(args):
    params = {"panelId": args.panel_id, "width": args.width, "height": args.height, "from": "now-1h", "to": "now"}
    path = f"/render/d-solo/{args.dashboard_uid}?{urlencode(params)}"
    try:
        raw = api(path, accept="image/png", raw=True)
        outfile = args.output or f"panel-{args.dashboard_uid}-{args.panel_id}.png"
        with open(outfile, "wb") as f:
            f.write(raw)
        print(f"Rendered -> {outfile} ({len(raw)} bytes)")
    except SystemExit:
        print("Render failed. Image Renderer plugin may not be installed.", file=sys.stderr)
        print(f"  Manual URL: {_grafana_base()}{path}", file=sys.stderr)
        raise


# ── Prometheus Query ──────────────────────────────────────────────────────────

def _find_prom_datasource():
    for ds in api("/api/datasources"):
        if ds.get("type") == "prometheus":
            return ds["id"], ds.get("name", "Prometheus")
    print("No Prometheus datasource found.", file=sys.stderr)
    sys.exit(1)


def _parse_duration(s):
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if s and s[-1] in units:
        return int(s[:-1]) * units[s[-1]]
    return int(s)


def cmd_query(args):
    ds_id, ds_name = _find_prom_datasource()
    params = urlencode({"query": args.promql, "time": int(time.time())})
    r = api(f"/api/datasources/proxy/{ds_id}/api/v1/query?{params}")
    data = r.get("data", {})
    results = data.get("result", [])
    print(f"Datasource: {ds_name} (id={ds_id})")
    print(f"Status: {r.get('status')}  |  Type: {data.get('resultType')}  |  Results: {len(results)}")
    print("-" * 90)
    for res in results:
        metric = res.get("metric", {})
        label = ", ".join(f'{k}="{v}"' for k, v in metric.items())
        val = res.get("value", [None, None])
        ts = datetime.fromtimestamp(val[0]).strftime("%H:%M:%S") if val[0] else "?"
        print(f"  {{{label}}}  @{ts}  = {val[1]}")
    if not results:
        print("  (no data)")


def cmd_query_range(args):
    ds_id, ds_name = _find_prom_datasource()
    now = int(time.time())
    start = now - _parse_duration(args.start)
    end = now if args.end == "now" else now - _parse_duration(args.end)
    step = int(args.step)
    params = urlencode({"query": args.promql, "start": start, "end": end, "step": step})
    r = api(f"/api/datasources/proxy/{ds_id}/api/v1/query_range?{params}")
    data = r.get("data", {})
    results = data.get("result", [])
    print(f"Datasource: {ds_name} (id={ds_id})")
    print(f"Range: -{args.start} -> {args.end}  |  Step: {step}s  |  Series: {len(results)}")
    print("-" * 90)
    for res in results:
        metric = res.get("metric", {})
        label = ", ".join(f'{k}="{v}"' for k, v in metric.items())
        values = res.get("values", [])
        print(f"\n  {{{label}}}  ({len(values)} samples)")
        for ts, val in values[:25]:
            t = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            print(f"    {t}  {val}")
        if len(values) > 25:
            print(f"    ... ({len(values) - 25} more)")


# ── Test Counters ─────────────────────────────────────────────────────────────

def _extract_expressions(dash):
    """Return list of (panel_title, expr, panel_id) from dashboard JSON."""
    results = []
    for p in dash.get("panels", []):
        if p.get("type") == "row":
            for sub in p.get("panels", []):
                for t in sub.get("targets", []):
                    expr = t.get("expr", "").strip()
                    if expr:
                        results.append((sub.get("title", ""), expr, sub.get("id", "")))
        else:
            for t in p.get("targets", []):
                expr = t.get("expr", "").strip()
                if expr:
                    results.append((p.get("title", ""), expr, p.get("id", "")))
    return results


def _strip_promql_to_metric(expr):
    """Extract base metric name(s) from a PromQL expression."""
    expr = re.sub(r'\$\w+\$?', '.*', expr)
    metrics = re.findall(r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*\{', expr)
    wrappers = {"sum", "rate", "avg", "min", "max", "count", "topk", "bottomk",
                "histogram_quantile", "increase", "irate", "delta", "deriv",
                "absent", "clamp", "clamp_max", "clamp_min", "label_replace",
                "label_join", "round", "sort", "sort_desc", "vector", "scalar",
                "on", "by", "without", "ignoring", "group_left", "group_right"}
    return [m for m in metrics if m.lower() not in wrappers]


def cmd_test_counters(args):
    source = args.source
    if os.path.isfile(source):
        with open(source, "r", encoding="utf-8") as f:
            payload = json.load(f)
        dash = payload.get("dashboard", payload)
        print(f"Source: local file {source}")
    else:
        r = api(f"/api/dashboards/uid/{source}")
        dash = r.get("dashboard", {})
        print(f"Source: live dashboard uid={source}")

    exprs = _extract_expressions(dash)
    print(f"Dashboard: {dash.get('title', 'N/A')}")
    print(f"Total expressions: {len(exprs)}\n")

    ds_id, ds_name = _find_prom_datasource()
    print(f"Testing against: {ds_name} (id={ds_id})")
    print("=" * 100)

    ok, empty, err = 0, 0, 0
    issues = []

    for title, expr, pid in exprs:
        clean_expr = re.sub(r'\$(\w+)\$?', '.*', expr)
        try:
            params = urlencode({"query": clean_expr, "time": int(time.time())})
            r = api(f"/api/datasources/proxy/{ds_id}/api/v1/query?{params}")
            results = r.get("data", {}).get("result", [])
            if results:
                ok += 1
                status = "OK"
            else:
                empty += 1
                status = "EMPTY"
                issues.append(("EMPTY", title, pid, expr))
        except SystemExit:
            err += 1
            status = "ERROR"
            issues.append(("ERROR", title, pid, expr))

        indicator = {"OK": "+", "EMPTY": "?", "ERROR": "!"}[status]
        print(f"  [{indicator}] Panel {pid:>3}  {title[:45]:<46} {status}")

    print("\n" + "=" * 100)
    print(f"Results: {ok} OK  |  {empty} EMPTY (no data)  |  {err} ERROR")

    if issues:
        print(f"\n--- Issues ({len(issues)}) ---")
        for kind, title, pid, expr in issues:
            print(f"\n  [{kind}] Panel {pid}: {title}")
            print(f"    expr: {expr[:120]}")
            for m in _strip_promql_to_metric(expr):
                print(f"    metric: {m}")
                print(f"    check:  curl '<prom>/api/v1/label/{m}/__name__/values'")

    print("\n--- Static Analysis ---")
    warns = _static_analysis(exprs)
    if warns:
        for w in warns:
            print(f"  WARN: {w}")
    else:
        print("  No issues found.")


def _static_analysis(exprs):
    """Check for common PromQL issues without hitting the server."""
    warns = []
    for title, expr, pid in exprs:
        if expr != expr.strip():
            warns.append(f"Panel {pid} '{title}': leading/trailing whitespace in expr")
        if re.search(r'pod="[^"]*-0"', expr) and '$instance' not in expr:
            warns.append(
                f"Panel {pid} '{title}': hardcoded pod ordinal '-0' — should use $instance variable"
            )
        if '$instance$' in expr and '$instance}' in expr:
            warns.append(
                f"Panel {pid} '{title}': mixed $instance$ and $instance usage in same panel"
            )
    return warns


# ── CLI Parser ────────────────────────────────────────────────────────────────

def build_parser():
    p = argparse.ArgumentParser(
        description="NSP Grafana API client",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("health", help="Check Grafana health")

    op = sub.add_parser("open", help="Print browser and JSON editor URLs for a dashboard")
    op.add_argument("uid")

    ds = sub.add_parser("datasources", help="Datasource operations")
    ds_sub = ds.add_subparsers(dest="ds_action")
    ds_sub.add_parser("list")

    da = sub.add_parser("dashboards", help="Dashboard operations")
    da_sub = da.add_subparsers(dest="da_action")
    da_sub.add_parser("list")

    s = da_sub.add_parser("search")
    s.add_argument("keyword")

    g = da_sub.add_parser("get")
    g.add_argument("uid")

    ex = da_sub.add_parser("export")
    ex.add_argument("uid")
    ex.add_argument("-o", "--output")

    im = da_sub.add_parser("import")
    im.add_argument("file")
    im.add_argument("--overwrite", action="store_true")

    ur = da_sub.add_parser("url", help="Extract UID from a Grafana URL and export")
    ur.add_argument("url")
    ur.add_argument("-o", "--output")

    di = da_sub.add_parser("diff")
    di.add_argument("uid")
    di.add_argument("file")

    pa = sub.add_parser("panels", help="Panel operations")
    pa_sub = pa.add_subparsers(dest="pa_action")
    pl = pa_sub.add_parser("list")
    pl.add_argument("dashboard_uid")
    pr = pa_sub.add_parser("render")
    pr.add_argument("dashboard_uid")
    pr.add_argument("panel_id")
    pr.add_argument("-o", "--output")
    pr.add_argument("--width", type=int, default=1000)
    pr.add_argument("--height", type=int, default=500)

    q = sub.add_parser("query", help="Instant PromQL query")
    q.add_argument("promql")

    qr = sub.add_parser("query-range", help="Range PromQL query")
    qr.add_argument("promql")
    qr.add_argument("--start", default="1h")
    qr.add_argument("--end", default="now")
    qr.add_argument("--step", default="60")

    tc = sub.add_parser("test-counters", help="Validate PromQL counters in a dashboard")
    tc.add_argument("source", help="Dashboard UID or local JSON file path")

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "health": cmd_health,
        "open": cmd_open,
        "datasources": lambda a: cmd_datasources_list(a),
        "dashboards": lambda a: {
            "list": cmd_dashboards_list,
            "search": cmd_dashboards_search,
            "get": cmd_dashboards_get,
            "export": cmd_dashboards_export,
            "import": cmd_dashboards_import,
            "url": cmd_dashboards_url,
            "diff": cmd_dashboards_diff,
        }.get(a.da_action, lambda _: print("Use: dashboards {list|search|get|export|import|url|diff}"))(a),
        "panels": lambda a: {
            "list": cmd_panels_list,
            "render": cmd_panels_render,
        }.get(a.pa_action, lambda _: print("Use: panels {list|render}"))(a),
        "query": cmd_query,
        "query-range": cmd_query_range,
        "test-counters": cmd_test_counters,
    }
    dispatch.get(args.cmd, lambda _: parser.print_help())(args)


if __name__ == "__main__":
    main()
