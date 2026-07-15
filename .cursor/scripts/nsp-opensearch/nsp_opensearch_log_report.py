#!/usr/bin/env python3
"""
NSP OpenSearch log rollup + Markdown report.

Prerequisites (same shell):
  source opensearch_env.sh

Uses REST Gateway client_credentials token, then POST _search (Query A / B from nsp-opensearch skill).

Examples:
  python3 nsp_opensearch_log_report.py --minutes 60 --output report.md
  python3 nsp_opensearch_log_report.py --minutes 1440 --query both --samples 5
  python3 nsp_opensearch_log_report.py --index nsp-mdm-server-logs-2026.04.10 --auto-widen
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any


def eprint(*args: object, **kwargs: object) -> None:
    print(*args, file=sys.stderr, **kwargs)


def split_gateway_host_port(gateway: str) -> tuple[str, int | None]:
    """
    Split NSP_GATEWAY into (host_for_opensearch, optional_gateway_port).
    Supports IPv4 host:port and IPv6 [::1]:8443.
    """
    g = gateway.strip()
    if g.startswith("["):
        end = g.find("]")
        if end == -1:
            return g, None
        host = g[: end + 1]
        rest = g[end + 1 :]
        if rest.startswith(":") and rest[1:].isdigit():
            return host, int(rest[1:])
        return host, None
    if ":" in g:
        # IPv4 host:port — last colon separates port if numeric
        host, maybe_port = g.rsplit(":", 1)
        if maybe_port.isdigit() and host.count(":") == 0:
            return host, int(maybe_port)
    return g, None


def ssl_context() -> ssl.SSLContext:
    verify = os.environ.get("NSP_VERIFY_TLS", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
    if verify:
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def http_request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None = None,
) -> tuple[int, Any]:
    ctx = ssl_context()
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    eprint(f"nsp_opensearch_log_report: {method} {url.split('?', 1)[0]}")
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode() if e.fp else ""
        try:
            parsed = json.loads(raw) if raw.strip() else {"message": raw}
        except json.JSONDecodeError:
            parsed = {"message": raw, "status": e.code}
        return e.code, parsed


def get_access_token(
    scheme: str,
    gateway_host: str,
    gateway_port: int | None,
    user: str,
    password: str,
) -> str:
    if gateway_port is not None:
        netloc = f"{gateway_host}:{gateway_port}"
    else:
        netloc = gateway_host
    token_url = f"{scheme}://{netloc}/rest-gateway/rest/api/v1/auth/token"
    basic = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = b"grant_type=client_credentials"
    status, data = http_request("POST", token_url, headers, body)
    if status != 200:
        eprint(f"Token request failed: HTTP {status} {data}")
        sys.exit(1)
    token = data.get("access_token")
    if not token:
        eprint("No access_token in response")
        sys.exit(1)
    return str(token)


def opensearch_search_url(
    scheme: str,
    opensearch_host: str,
    opensearch_port: str,
    index: str | None,
) -> str:
    base = f"{scheme}://{opensearch_host}:{opensearch_port}"
    if index:
        return f"{base}/{urllib.parse.quote(index, safe='')}/_search"
    return f"{base}/_search"


def format_ts(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    s = dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return s


def total_hits(data: dict[str, Any]) -> int:
    t = data.get("hits", {}).get("total", 0)
    if isinstance(t, dict):
        return int(t.get("value", 0))
    return int(t or 0)


ERROR_LEVELS = ["ERROR", "exception", "Exception", "Error", "E"]


def query_body_error_rollup(gte: str, lte: str, index_sizes: tuple[int, int, int]) -> dict[str, Any]:
    sz_idx, sz_app, sz_file = index_sizes
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@datetime": {
                                "gte": gte,
                                "lte": lte,
                                "format": "strict_date_optional_time",
                            }
                        }
                    },
                    {"terms": {"LogLevel.keyword": ERROR_LEVELS}},
                ]
            }
        },
        "aggs": {
            "by_index": {
                "terms": {
                    "field": "_index",
                    "size": sz_idx,
                    "order": [{"_count": "desc"}],
                },
                "aggs": {
                    "by_app": {
                        "terms": {
                            "field": "AppName.keyword",
                            "size": sz_app,
                            "order": [{"_count": "desc"}],
                        },
                        "aggs": {
                            "by_log_file": {
                                "terms": {
                                    "field": "log_file.keyword",
                                    "size": sz_file,
                                    "order": [{"_count": "desc"}],
                                    "missing": "(no log_file)",
                                }
                            }
                        },
                    }
                },
            }
        },
    }


def query_body_level_breakdown(gte: str, lte: str, index_sizes: tuple[int, int, int]) -> dict[str, Any]:
    sz_idx, sz_app, sz_file = index_sizes
    return {
        "size": 0,
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@datetime": {
                                "gte": gte,
                                "lte": lte,
                                "format": "strict_date_optional_time",
                            }
                        }
                    }
                ]
            }
        },
        "aggs": {
            "by_index": {
                "terms": {
                    "field": "_index",
                    "size": sz_idx,
                    "order": [{"_count": "desc"}],
                },
                "aggs": {
                    "by_app": {
                        "terms": {
                            "field": "AppName.keyword",
                            "size": sz_app,
                            "order": [{"_count": "desc"}],
                        },
                        "aggs": {
                            "by_log_file": {
                                "terms": {
                                    "field": "log_file.keyword",
                                    "size": sz_file,
                                    "order": [{"_count": "desc"}],
                                    "missing": "(no log_file)",
                                },
                                "aggs": {
                                    "by_level": {
                                        "terms": {
                                            "field": "LogLevel.keyword",
                                            "size": 10,
                                            "order": [{"_count": "desc"}],
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
            }
        },
    }


def query_body_samples(gte: str, lte: str, sample_size: int) -> dict[str, Any]:
    return {
        "size": sample_size,
        "query": {
            "bool": {
                "filter": [
                    {
                        "range": {
                            "@datetime": {
                                "gte": gte,
                                "lte": lte,
                                "format": "strict_date_optional_time",
                            }
                        }
                    },
                    {"terms": {"LogLevel.keyword": ERROR_LEVELS}},
                ]
            }
        },
        "sort": [{"@datetime": {"order": "desc", "unmapped_type": "date"}}],
    }


def run_search(
    url: str,
    bearer: str,
    body: dict[str, Any],
) -> dict[str, Any]:
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {bearer}",
    }
    status, data = http_request(
        "POST",
        url,
        headers,
        json.dumps(body).encode("utf-8"),
    )
    if status not in (200, 201):
        eprint(f"OpenSearch _search failed: HTTP {status}")
        eprint(json.dumps(data, indent=2)[:4000])
        sys.exit(1)
    return data


def flatten_rollup_rows(data: dict[str, Any], max_rows: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    by_index = (data.get("aggregations") or {}).get("by_index") or {}
    for ib in by_index.get("buckets") or []:
        idx = ib.get("key", "")
        for ab in (ib.get("by_app") or {}).get("buckets") or []:
            app = ab.get("key", "")
            for fb in (ab.get("by_log_file") or {}).get("buckets") or []:
                rows.append(
                    {
                        "index": idx,
                        "app": app,
                        "log_file": fb.get("key", ""),
                        "count": fb.get("doc_count", 0),
                    }
                )
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:max_rows]


def flatten_level_rows(
    data: dict[str, Any],
    max_rows: int,
) -> list[dict[str, Any]]:
    """Rows for error-class levels only (Query B)."""
    rows: list[dict[str, Any]] = []
    err_set = set(ERROR_LEVELS)
    by_index = (data.get("aggregations") or {}).get("by_index") or {}
    for ib in by_index.get("buckets") or []:
        idx = ib.get("key", "")
        for ab in (ib.get("by_app") or {}).get("buckets") or []:
            app = ab.get("key", "")
            for fb in (ab.get("by_log_file") or {}).get("buckets") or []:
                lf = fb.get("key", "")
                for lb in (fb.get("by_level") or {}).get("buckets") or []:
                    lvl = str(lb.get("key", ""))
                    if lvl in err_set:
                        rows.append(
                            {
                                "index": idx,
                                "app": app,
                                "log_file": lf,
                                "level": lvl,
                                "count": lb.get("doc_count", 0),
                            }
                        )
    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows[:max_rows]


def hits_to_samples(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for h in hits:
        src = h.get("_source") or {}
        out.append(
            {
                "@datetime": src.get("@datetime", ""),
                "index": h.get("_index", ""),
                "AppName": src.get("AppName", ""),
                "LogLevel": src.get("LogLevel", ""),
                "log_file": src.get("log_file", ""),
                "LogMessage": (src.get("LogMessage") or "")[:500],
            }
        )
    return out


def markdown_report(
    *,
    gateway: str,
    search_url: str,
    gte: str,
    lte: str,
    minutes: int,
    rollup_rows: list[dict[str, Any]] | None,
    level_rows: list[dict[str, Any]] | None,
    samples: list[dict[str, Any]] | None,
) -> str:
    lines = [
        "# NSP OpenSearch log analysis report",
        "",
        f"**Generated (UTC):** {format_ts(datetime.now(timezone.utc))}",
        f"**NSP gateway host:** `{gateway}`",
        f"**Search URL:** `{search_url}`",
        f"**Time window:** `{gte}` → `{lte}` (~{minutes} minutes)",
        "",
        "## Summary",
        "",
    ]
    if rollup_rows is not None:
        lines.append("### Error rollup (index × AppName × log_file)")
        lines.append("")
        lines.append("| Count | Index | AppName | log_file |")
        lines.append("|------:|-------|---------|----------|")
        for r in rollup_rows:
            lines.append(
                f"| {r['count']} | `{r['index']}` | {r['app']} | {r['log_file']} |"
            )
        lines.append("")
    if level_rows is not None:
        lines.append("### Error-level breakdown (Query B subset)")
        lines.append("")
        lines.append("| Count | Index | AppName | log_file | LogLevel |")
        lines.append("|------:|-------|---------|----------|----------|")
        for r in level_rows:
            lines.append(
                f"| {r['count']} | `{r['index']}` | {r['app']} | {r['log_file']} | {r['level']} |"
            )
        lines.append("")
    if samples:
        lines.append("## Recent error samples (newest first)")
        lines.append("")
        for i, s in enumerate(samples, 1):
            lines.append(f"### Sample {i}")
            lines.append("")
            lines.append(f"- **@datetime:** {s.get('@datetime')}")
            lines.append(f"- **Index:** `{s.get('index')}`")
            lines.append(f"- **AppName:** {s.get('AppName')}")
            lines.append(f"- **LogLevel:** {s.get('LogLevel')}")
            lines.append(f"- **log_file:** {s.get('log_file')}")
            msg = s.get("LogMessage") or ""
            lines.append("")
            lines.append("```text")
            lines.append(msg.replace("```", "``\\`"))
            lines.append("```")
            lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Report produced by `nsp_opensearch_log_report.py` (agentic-workspace).*")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="NSP OpenSearch error rollup → Markdown report")
    ap.add_argument("--minutes", type=int, default=60, help="Lookback window in minutes (default 60)")
    ap.add_argument(
        "--query",
        choices=("a", "b", "both"),
        default="a",
        help="a=error rollup only, b=level breakdown (error rows), both",
    )
    ap.add_argument("--samples", type=int, default=0, help="Include N recent error hits (default 0)")
    ap.add_argument("--index", default=None, help="Restrict to a single index name")
    ap.add_argument("--output", "-o", default="-", help="Markdown output file, or - for stdout")
    ap.add_argument("--top", type=int, default=20, help="Max table rows per section (default 20)")
    ap.add_argument(
        "--agg-size",
        default="100,50,20",
        help="Comma sizes for terms aggs: index,app,log_file (default 100,50,20)",
    )
    ap.add_argument(
        "--auto-widen",
        action="store_true",
        help="If rollup has zero buckets, retry once with 24h window",
    )
    ap.add_argument("--json-out", action="store_true", help="Print raw JSON (rollup) to stdout instead of MD")
    args = ap.parse_args()

    gateway = os.environ.get("NSP_GATEWAY") or os.environ.get("NSP_IP", "")
    user = os.environ.get("NSP_USER", "")
    password = os.environ.get("NSP_PASSWORD", "")
    if not gateway or not user or not password:
        eprint("Set NSP_GATEWAY (or NSP_IP), NSP_USER, NSP_PASSWORD (source opensearch_env.sh)")
        sys.exit(1)

    scheme = os.environ.get("NSP_HTTPS_SCHEME", "https").strip()
    opensearch_port = os.environ.get("NSP_OPENSEARCH_PORT", "9200").strip()

    host_only, gw_port = split_gateway_host_port(gateway)
    token = get_access_token(scheme, host_only, gw_port, user, password)

    search_url = opensearch_search_url(scheme, host_only, opensearch_port, args.index)

    parts = [int(x.strip()) for x in args.agg_size.split(",")]
    while len(parts) < 3:
        parts.append(20)
    sizes = (parts[0], parts[1], parts[2])

    now = datetime.now(timezone.utc)
    minutes = args.minutes
    lte = format_ts(now)
    gte = format_ts(now - timedelta(minutes=minutes))

    def do_rollup(gte_s: str, lte_s: str) -> dict[str, Any]:
        body = query_body_error_rollup(gte_s, lte_s, sizes)
        return run_search(search_url, token, body)

    data_a = do_rollup(gte, lte)
    buckets = ((data_a.get("aggregations") or {}).get("by_index") or {}).get("buckets") or []

    if args.auto_widen and not buckets and minutes <= 1440:
        eprint("No rollup buckets in window; widening to 24h (UTC)")
        minutes = 1440
        gte = format_ts(now - timedelta(minutes=minutes))
        data_a = do_rollup(gte, lte)
        buckets = ((data_a.get("aggregations") or {}).get("by_index") or {}).get("buckets") or []

    if args.json_out:
        print(json.dumps(data_a, indent=2))
        return

    rollup_rows = None
    level_rows = None
    if args.query in ("a", "both"):
        rollup_rows = flatten_rollup_rows(data_a, args.top)
    if args.query in ("b", "both"):
        body_b = query_body_level_breakdown(gte, lte, sizes)
        data_b = run_search(search_url, token, body_b)
        level_rows = flatten_level_rows(data_b, args.top)

    samples: list[dict[str, Any]] | None = None
    if args.samples > 0:
        body_s = query_body_samples(gte, lte, args.samples)
        data_s = run_search(search_url, token, body_s)
        hits = (data_s.get("hits") or {}).get("hits") or []
        samples = hits_to_samples(hits)

    md = markdown_report(
        gateway=gateway,
        search_url=search_url,
        gte=gte,
        lte=lte,
        minutes=minutes,
        rollup_rows=rollup_rows,
        level_rows=level_rows,
        samples=samples,
    )

    if args.output == "-":
        print(md)
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(md)
        eprint(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
