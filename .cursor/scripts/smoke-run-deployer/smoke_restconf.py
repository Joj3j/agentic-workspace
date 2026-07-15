#!/usr/bin/env python3
"""
NSP RESTCONF smoke tool for the data deployer (epipe + ip-filter).

Prerequisites (same shell):
  source restconf_env.sh

Examples:
  python3 smoke_restconf.py list-nes
  python3 smoke_restconf.py list-lags --ne 192.168.96.79
  python3 smoke_restconf.py list-sdps --ne 192.168.96.79
  python3 smoke_restconf.py deploy --ne 192.168.96.79 --count 10 --lag lag-59 --sdp 2
  python3 smoke_restconf.py deploy --ne 192.168.96.79 --count 100 --lag lag-59 --sdp 2 --base 3000 --max-batch 8
  # service-name pattern: ep-ag-smoke-{ID}, filter-name pattern: filter-ag-smoke-{ID}
  python3 smoke_restconf.py check --request-id 4
  python3 smoke_restconf.py check --all
  python3 smoke_restconf.py delete --request-id 4
  python3 smoke_restconf.py delete --all
  python3 smoke_restconf.py cleanup --ne 192.168.96.79
  python3 smoke_restconf.py cleanup --ne 192.168.96.79 --base 3000 --count 10
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import json
import os
import random
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_print_lock = threading.Lock()

STATE_FILE    = Path.home() / ".smoke_restconf_state.json"
NE_CACHE_FILE = Path.home() / ".smoke_ne_cache.json"

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def eprint(*args: object, **kwargs: object) -> None:
    print(*args, file=sys.stderr, **kwargs)


def ssl_context() -> ssl.SSLContext:
    verify = os.environ.get("NSP_VERIFY_TLS", "0").strip().lower() not in ("0", "false", "no", "off")
    if verify:
        return ssl.create_default_context()
    return ssl._create_unverified_context()


def http_request(
    method: str,
    url: str,
    headers: dict[str, str],
    body: bytes | None = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    ctx = ssl_context()
    req = urllib.request.Request(url, data=body, method=method)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=timeout) as resp:
            raw = resp.read()
            try:
                return resp.status, json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                return resp.status, raw.decode(errors="replace")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = raw.decode(errors="replace")
        return exc.code, payload


def gateway() -> str:
    gw = os.environ.get("NSP_GATEWAY", "").strip()
    if not gw:
        sys.exit("NSP_GATEWAY not set. Run: source restconf_env.sh")
    return gw


def restconf_port() -> str:
    return os.environ.get("RESTCONF_PORT", "8545").strip()


def scheme() -> str:
    return os.environ.get("NSP_HTTPS_SCHEME", "https").strip()


def restconf_base() -> str:
    return f"{scheme()}://{gateway()}:{restconf_port()}/restconf"


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def get_token() -> str:
    gw = gateway()
    user = os.environ.get("NSP_USER", "").strip()
    password = os.environ.get("NSP_PASSWORD", "").strip()
    if not user or not password:
        sys.exit("NSP_USER or NSP_PASSWORD not set. Run: source restconf_env.sh")

    token_url = f"{scheme()}://{gw}/rest-gateway/rest/api/v1/auth/token"
    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    body = b"grant_type=client_credentials"
    eprint(f"AUTH  POST {token_url}")
    status, data = http_request("POST", token_url, headers, body)
    if status != 200 or not isinstance(data, dict):
        sys.exit(f"Token request failed ({status}): {data}")
    token = data.get("access_token", "")
    if not token:
        sys.exit(f"No access_token in response: {data}")
    return token


def bearer_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/yang-data+json",
    }


def yang_patch_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/yang-patch+json",
        "Accept": "application/yang-data+json",
    }


# ---------------------------------------------------------------------------
# Pretty table
# ---------------------------------------------------------------------------

def print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    widths = {c: len(c) for c in columns}
    for row in rows:
        for c in columns:
            widths[c] = max(widths[c], len(str(row.get(c, ""))))
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    sep = "  ".join("-" * widths[c] for c in columns)
    print(header)
    print(sep)
    for row in rows:
        print("  ".join(str(row.get(c, "")).ljust(widths[c]) for c in columns))


# ---------------------------------------------------------------------------
# State file (tracks request-ids + deploy params)
# ---------------------------------------------------------------------------

def load_state() -> dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"deploys": []}


def save_state(state: dict[str, Any]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def record_deploy(
    state: dict[str, Any],
    ne: str,
    base: int,
    count: int,
    request_ids: list[int],
    patch_ids: list[str],
    kind: str = "deploy",
    filter_base: int | None = None,
) -> None:
    state.setdefault("deploys", []).append(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kind": kind,
            "ne": ne,
            "base": base,
            "filter_base": filter_base if filter_base is not None else base,
            "count": count,
            "request_ids": request_ids,
            "patch_ids": patch_ids,
        }
    )


def last_deploy(state: dict[str, Any]) -> dict[str, Any] | None:
    deploys = [d for d in state.get("deploys", []) if d.get("kind") == "deploy"]
    return deploys[-1] if deploys else None


# ---------------------------------------------------------------------------
# Batch generation
# ---------------------------------------------------------------------------

def gen_deploy_batches(count: int, max_batch: int) -> list[int]:
    """Randomly varying batch sizes in [2, max_batch], never a single shot."""
    if max_batch < 2:
        max_batch = 2
    batches: list[int] = []
    remaining = count
    while remaining > 0:
        hi = min(max_batch, remaining)
        lo = min(2, hi)
        size = random.randint(lo, hi)
        batches.append(size)
        remaining -= size
    return batches


def gen_cleanup_batches(count: int) -> list[int]:
    """1 or 2 shots for cleanup."""
    if count <= 1:
        return [count]
    half = count // 2
    return [half, count - half]


# ---------------------------------------------------------------------------
# YANG PATCH body builders
# ---------------------------------------------------------------------------

def svc_name(service_id: int) -> str:
    return f"ep-ag-smoke-{service_id}"


def filter_name(filter_id: int) -> str:
    return f"filter-ag-smoke-{filter_id}"


def epipe_edit(edit_idx: int, service_id: int, lag: str, vlan: int, sdp: str, total_count: int) -> dict:
    # Standard SROS epipe supports a single spoke-sdp (two requires vc-switch mode).
    name = svc_name(service_id)
    return {
        "edit-id": f"edit-{edit_idx}",
        "operation": "merge",
        "target": f"nokia-conf:configure/service/epipe={service_id}",
        "value": {
            "nokia-conf:epipe": {
                "service-name": name,
                "service-id": service_id,
                "description": f"smoke {name}",
                "service-mtu": 1514,
                "admin-state": "enable",
                "customer": "1",
                "sap": [
                    {
                        "sap-id": f"{lag}:{vlan}",
                        "description": f"smoke sap {name}",
                        "admin-state": "disable",
                    }
                ],
                "spoke-sdp": [
                    {
                        "sdp-bind-id": f"{sdp}:{service_id}",
                        "vc-type": "vlan",
                        "description": f"smoke sdp {name}",
                        "admin-state": "enable",
                    },
                ],
            }
        },
    }


def _filter_entries(fname: str) -> list[dict]:
    """Return 3 ip-filter entry blocks with random unique entry-ids (1–100)."""
    ids = sorted(random.sample(range(1, 101), 3))
    return [
        {
            "entry-id": str(ids[0]),
            "description": f"smoke entry-a {fname}",
            "pbr-down-action-override": "drop",
        },
        {
            "entry-id": str(ids[1]),
            "description": f"smoke entry-b {fname}",
            "pbr-down-action-override": "forward",
            "egress-pbr": "true-with-l4lb",
        },
        {
            "entry-id": str(ids[2]),
            "description": f"smoke entry-c {fname}",
            "pbr-down-action-override": "filter-default-action",
            "filter-sample": "true",
            "interface-sample": "false",
        },
    ]


def filter_edit(edit_idx: int, filter_id: int) -> dict:
    # Target must include the list key (filter-name) so the deployer creates
    # the specific entry rather than merging against the parent list.
    fname = filter_name(filter_id)
    return {
        "edit-id": f"edit-{edit_idx}",
        "operation": "merge",
        "target": f"nokia-conf:configure/filter/ip-filter={fname}",
        "value": {
            "nokia-conf:ip-filter": {
                "filter-name": fname,
                "filter-id": filter_id,
                "default-action": "drop",
                "scope": "exclusive",
                "description": f"smoke {fname}",
                "type": "normal",
                "shared-policer": "false",
                "chain-to-system-filter": "false",
                "entry": _filter_entries(fname),
            }
        },
    }


def epipe_remove(edit_idx: int, service_id: int) -> dict:
    # Target uses service-name, matching the name set at creation.
    return {
        "edit-id": f"edit-{edit_idx}",
        "operation": "remove",
        "target": f"nokia-conf:/configure/service/epipe={svc_name(service_id)}",
    }


def filter_remove(edit_idx: int, filter_id: int) -> dict:
    # Target uses filter-name, matching the name set at creation.
    return {
        "edit-id": f"edit-{edit_idx}",
        "operation": "remove",
        "target": f"nokia-conf:/configure/filter/ip-filter={filter_name(filter_id)}",
    }


def build_patch_body(patch_id: str, edits: list[dict]) -> bytes:
    body = {
        "ietf-yang-patch:yang-patch": {
            "patch-id": patch_id,
            "edit": edits,
        }
    }
    return json.dumps(body).encode()


def submit_patch(token: str, ne_id: str, patch_id: str, edits: list[dict],
                 timeout: float = 120.0) -> tuple[int | None, float]:
    """Submit a YANG PATCH and return (request-id, http_elapsed_ms)."""
    url = (
        f"{restconf_base()}/data/nsp-network:network/node={ne_id}/node-root"
    )
    body = build_patch_body(patch_id, edits)
    t0 = time.monotonic()
    try:
        status, data = http_request("PATCH", url, yang_patch_headers(token), body, timeout=timeout)
    except Exception as exc:
        elapsed_ms = (time.monotonic() - t0) * 1000
        print(f"    NETWORK ERROR ({elapsed_ms:.0f}ms): {exc}")
        return None, elapsed_ms
    elapsed_ms = (time.monotonic() - t0) * 1000
    if status in (200, 202):
        req_id = None
        if isinstance(data, dict):
            submitted = data.get("Submitted", {})
            req_id = submitted.get("request-id")
        print(f"    submitted → request-id={req_id}  (HTTP {status}  {elapsed_ms:.0f}ms)")
        return req_id, elapsed_ms
    else:
        print(f"    ERROR HTTP {status}: {json.dumps(data, indent=2) if isinstance(data, dict) else data}")
        return None, elapsed_ms


# ---------------------------------------------------------------------------
# Deployer status polling + bulk approximation
# ---------------------------------------------------------------------------

def _check_deployer_status(token: str, rid: int) -> tuple[str, str]:
    """Return (status, error_msg).  status ∈ {SUCCESS, FAILED, PENDING, HTTP_<N>}."""
    url = f"{restconf_base()}/data/nsp-deployer:deployers/plugin=mdm/deployer={rid}?depth=1"
    status, data = http_request("GET", url, bearer_headers(token))
    if status == 404:
        return "SUCCESS", ""
    if status == 200:
        err = ""
        if isinstance(data, dict):
            for obj in data.values():
                if isinstance(obj, dict):
                    err = obj.get("error-message", "")
                    if err:
                        break
        return ("FAILED" if err else "PENDING"), err
    return f"HTTP_{status}", str(data)[:80]


def poll_until_done(
    token: str,
    req_ids: list[int],
    t_start: float,
    poll_interval: float = 2.0,
    timeout: float = 120.0,
    poll_workers: int = 20,
) -> dict[int, dict]:
    """Poll deployer for all req_ids until done or timeout.

    Uses a thread pool for parallel HTTP checks so large batches (1000+ requests)
    don't serialize into an impractically long poll cycle.

    Returns dict[rid -> {status, elapsed_ms, finish_ts, error}].
    """
    pending = {r for r in req_ids if r is not None}
    results: dict[int, dict] = {}
    deadline = time.monotonic() + timeout
    workers = min(poll_workers, len(pending)) if pending else 1
    print(f"\nWaiting for {len(pending)} deployer request(s)"
          f"  poll={poll_interval}s  timeout={timeout}s  poll_workers={workers}")

    def _check_one(rid: int) -> tuple[int, str, str]:
        try:
            st, err = _check_deployer_status(token, rid)
        except Exception as exc:
            # Transient network error — treat as PENDING and retry next cycle
            return rid, "PENDING", ""
        return rid, st, err

    while pending and time.monotonic() < deadline:
        time.sleep(poll_interval)
        t_now_ref = time.monotonic()
        newly_done: list[int] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            for rid, st, err in pool.map(_check_one, list(pending)):
                if st == "PENDING":
                    continue
                t_now = time.monotonic()
                elapsed = (t_now - t_start) * 1000
                results[rid] = {"status": st, "elapsed_ms": elapsed,
                                 "finish_ts": t_now, "error": err}
                newly_done.append(rid)

        for rid in newly_done:
            pending.discard(rid)
            r = results[rid]
            err_str = f"  err={r['error'][:60]}" if r.get("error") else ""
            print(f"  req={rid:<6}  {r['status']:<10}  +{r['elapsed_ms']/1000:.2f}s{err_str}")

        if newly_done:
            still = len(pending)
            if still:
                print(f"  … {still} still pending")

    for rid in pending:
        t_now = time.monotonic()
        elapsed = (t_now - t_start) * 1000
        results[rid] = {"status": "TIMEOUT", "elapsed_ms": elapsed,
                        "finish_ts": t_now, "error": "timeout"}
        print(f"  req={rid:<6}  TIMEOUT    +{elapsed/1000:.2f}s")
    return results


def approx_bulk_groups(finish_ts_list: list[float], window_s: float = 1.0) -> list[int]:
    """Group monotonic finish timestamps into likely bulk dispatch groups.

    Requests finishing within window_s of each other were probably co-batched
    by comm-layer-server.  Returns list of per-group sizes.
    """
    if not finish_ts_list:
        return []
    sorted_ts = sorted(finish_ts_list)
    groups: list[list[float]] = [[sorted_ts[0]]]
    for ts in sorted_ts[1:]:
        if ts - groups[-1][-1] <= window_s:
            groups[-1].append(ts)
        else:
            groups.append([ts])
    return [len(g) for g in groups]


def print_ne_timing_table(
    ne_req_ids: dict[str, list[int]],
    finish_results: dict[int, dict],
    ne_first_submit_ts: dict[str, float] | None = None,
) -> None:
    """Fixed per-NE timing table: NE | Batches | E2E | Status.

    E2E = time from when the NE's first PATCH was submitted (202 received)
    to when its last deployer result was confirmed (SUCCESS or FAILED).
    """
    rows = []
    for ne in sorted(ne_req_ids):
        rids = ne_req_ids[ne]
        fr_list = [finish_results[r] for r in rids if r in finish_results]
        if not fr_list:
            rows.append({"NE": ne, "Batches": len(rids), "E2E": "?", "Status": "?"})
            continue
        last_finish_ts = max(r["finish_ts"] for r in fr_list)
        if ne_first_submit_ts and ne in ne_first_submit_ts:
            e2e = last_finish_ts - ne_first_submit_ts[ne]
        else:
            e2e = max(r["elapsed_ms"] for r in fr_list) / 1000
        statuses = "/".join(sorted({r["status"] for r in fr_list}))
        rows.append({
            "NE": ne,
            "Batches": len(rids),
            "E2E": f"{e2e:.2f}s",
            "Status": statuses,
        })
    print()
    print_table(rows, ["NE", "Batches", "E2E", "Status"])


def format_bulk_summary(finish_ts_list: list[float], window_s: float = 1.0) -> str:
    """Return a human-readable bulk approximation sentence."""
    groups = approx_bulk_groups(finish_ts_list, window_s)
    if not groups:
        return ""
    total = sum(groups)
    n = len(groups)
    if n == 1:
        return (f"All {total} requests were processed in a single bulk group "
                f"— full bulking by comm-layer-server.")
    sizes_str = ", ".join(str(g) for g in groups[:-1]) + f" and {groups[-1]}"
    max_g = max(groups)
    pct = int(max_g / total * 100)
    quality = "well" if pct >= 50 else "partially"
    detail = (f"the largest group ({max_g}) covered {pct}% of submissions"
              if pct >= 50 else f"split across {n} waves")
    return (f"The {total} requests grouped into {n} bulk groups (sizes {sizes_str}), "
            f"meaning comm-layer-server batched them {quality} — {detail}.")


def _print_timing_summary(
    work: list[tuple[int, str, list[dict], str]],
    submit_elapsed: dict[int, float],
    results: dict[int, int | None],
    finish_results: dict[int, dict],
    t_start: float,
    t_all_submitted: float,
    bulk_window_s: float,
) -> None:
    """Print per-batch timing table, total wall time, and bulk approximation."""
    rows = []
    for k, pid, _, svc_range in work:
        req_id = results.get(k)
        fr = finish_results.get(req_id, {}) if req_id is not None else {}
        rows.append({
            "batch": k,
            "req-id": req_id if req_id is not None else "ERR",
            "submit_ms": f"{submit_elapsed.get(k, 0):.0f}",
            "finish_s": f"{fr['elapsed_ms']/1000:.2f}" if fr.get("elapsed_ms") is not None else "?",
            "status": fr.get("status", "?"),
        })

    print("\nTiming summary (submit_ms = HTTP 202 round-trip; finish_s = from t0 to deployer done):")
    print_table(rows, ["batch", "req-id", "submit_ms", "finish_s", "status"])

    submit_wall = t_all_submitted - t_start
    if finish_results:
        total_wall = max(r["finish_ts"] for r in finish_results.values()) - t_start
        print(f"\nWall time:  submit_wall={submit_wall:.2f}s  total={total_wall:.2f}s")
        finish_ts_list = [r["finish_ts"] for r in finish_results.values()]
        groups = approx_bulk_groups(finish_ts_list, window_s=bulk_window_s)
        if groups:
            avg = sum(groups) / len(groups)
            print(f"Bulk approx ({bulk_window_s}s window):  groups={len(groups)}"
                  f"  sizes={groups}  avg={avg:.1f}")
    else:
        print(f"\nSubmit wall: {submit_wall:.2f}s")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list_nes(args: argparse.Namespace, token: str) -> None:
    url = f"{restconf_base()}/meta/api/v1/nes"
    eprint(f"GET  {url}")
    status, data = http_request("GET", url, bearer_headers(token))
    if status != 200:
        sys.exit(f"list-nes failed ({status}): {data}")

    nes: list[dict] = []
    if isinstance(data, dict):
        # Try common response shapes
        for key in ("ne", "nes", "network-element", "items", "data"):
            if key in data:
                val = data[key]
                nes = val if isinstance(val, list) else [val]
                break
        if not nes:
            # Flatten top-level if it's a list at root
            for v in data.values():
                if isinstance(v, list):
                    nes = v
                    break
    elif isinstance(data, list):
        nes = data

    if not nes:
        print("No NEs found. Raw response:")
        print(json.dumps(data, indent=2))
        return

    seen: set[str] = set()
    rows = []
    for ne in nes:
        if not isinstance(ne, dict):
            continue
        ne_id = ne.get("neId") or ne.get("ne-id") or ne.get("id", "")
        if ne_id in seen:
            continue
        seen.add(ne_id)
        rows.append(
            {
                "neId": ne_id,
                "type": ne.get("type") or ne.get("ne-type") or ne.get("neType", ""),
                "version": ne.get("version") or ne.get("sw-version") or ne.get("swVersion", ""),
            }
        )

    if rows:
        print(f"\nAvailable NEs on {gateway()}:\n")
        print_table(rows, ["neId", "type", "version"])
        print(f"\nTotal: {len(rows)}")
    else:
        print("No NEs parsed. Raw response:")
        print(json.dumps(data, indent=2))


def cmd_list_lags(args: argparse.Namespace, token: str) -> None:
    ne = args.ne
    url = (
        f"{restconf_base()}/data/network-device-mgr:network-devices"
        f"/network-device={ne}/root/nokia-conf:/configure/lag?depth=1"
    )
    eprint(f"GET  {url}")
    status, data = http_request("GET", url, bearer_headers(token))
    if status != 200:
        sys.exit(f"list-lags failed ({status}): {data}")

    lags: list[dict] = []
    if isinstance(data, dict):
        for key in ("lag", "nokia-conf:lag"):
            if key in data:
                val = data[key]
                lags = val if isinstance(val, list) else [val]
                break

    if not lags:
        print("No LAGs found. Raw response:")
        print(json.dumps(data, indent=2))
        return

    rows = [{"lag-name": lg.get("lag-name", ""), "admin-state": lg.get("admin-state", "")} for lg in lags if isinstance(lg, dict)]
    print(f"\nLAGs on NE {ne}:\n")
    print_table(rows, ["lag-name", "admin-state"])


def cmd_list_sdps(args: argparse.Namespace, token: str) -> None:
    ne = args.ne
    url = (
        f"{restconf_base()}/data/network-device-mgr:network-devices"
        f"/network-device={ne}/root/nokia-conf:/configure/service/sdp?depth=1"
    )
    eprint(f"GET  {url}")
    status, data = http_request("GET", url, bearer_headers(token))
    if status != 200:
        sys.exit(f"list-sdps failed ({status}): {data}")

    sdps: list[dict] = []
    if isinstance(data, dict):
        for key in ("sdp", "nokia-conf:sdp"):
            if key in data:
                val = data[key]
                sdps = val if isinstance(val, list) else [val]
                break

    if not sdps:
        print("No SDPs found. Raw response:")
        print(json.dumps(data, indent=2))
        return

    rows = [
        {
            "sdp-id": s.get("sdp-id", ""),
            "far-end": s.get("far-end", ""),
            "admin-state": s.get("admin-state", ""),
        }
        for s in sdps
        if isinstance(s, dict)
    ]
    print(f"\nSDPs on NE {ne}:\n")
    print_table(rows, ["sdp-id", "far-end", "admin-state"])


def cmd_deploy(args: argparse.Namespace, token: str, state: dict) -> None:
    ne = args.ne
    count = args.count
    base = args.base
    filter_base = args.filter_base if args.filter_base is not None else base
    if filter_base + count - 1 > 65535:
        sys.exit(f"filter-id {filter_base}+{count-1}={filter_base+count-1} exceeds max 65535. Use --filter-base with a lower value.")
    lag = args.lag
    sdp = args.sdp
    vlan_start = args.vlan_start
    max_batch = args.max_batch
    threads = args.threads

    batches = gen_deploy_batches(count, max_batch)
    total_batches = len(batches)
    print(
        f"\nDeploy {count} epipes + {count} ip-filters on NE {ne}"
        f"  base={base}  lag={lag}  sdp={sdp}"
        f"  vlan-start={vlan_start}  max-batch={max_batch}  threads={threads}"
        f"\nBatch plan ({total_batches} requests): {batches}\n"
    )

    # Pre-compute all batch work items so threads can fire simultaneously.
    work: list[tuple[int, str, list[dict], str]] = []  # (k, patch_id, edits, svc_range)
    offset = 0
    for k, batch_size in enumerate(batches, start=1):
        ids = list(range(base + offset, base + offset + batch_size))
        patch_id = f"smoke-{base}-batch{k}"
        edits: list[dict] = []
        for j, sid in enumerate(ids):
            vlan = vlan_start + offset + j
            edits.append(epipe_edit(j + 1, sid, lag, vlan, sdp, count))
        for j in range(len(ids)):
            fid = filter_base + offset + j
            edits.append(filter_edit(batch_size + j + 1, fid))
        svc_range = f"{svc_name(ids[0])}–{svc_name(ids[-1])}" if len(ids) > 1 else svc_name(ids[0])
        work.append((k, patch_id, edits, svc_range))
        offset += batch_size

    results: dict[int, int | None] = {}   # k → request_id
    submit_elapsed: dict[int, float] = {} # k → HTTP round-trip ms

    t_start = time.monotonic()

    def _submit(item: tuple[int, str, list[dict], str]) -> tuple[int, int | None]:
        k, patch_id, edits, svc_range = item
        with _print_lock:
            print(f"  Batch {k}/{total_batches}  {svc_range}  ({len(edits)} edits)  patch-id={patch_id}")
        req_id, elapsed = submit_patch(token, ne, patch_id, edits)
        with _print_lock:
            submit_elapsed[k] = elapsed
        return k, req_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(_submit, item) for item in work]
        for fut in concurrent.futures.as_completed(futures):
            k, req_id = fut.result()
            results[k] = req_id

    t_all_submitted = time.monotonic()

    # Collect in original order
    patch_ids = [w[1] for w in work]
    request_ids = [results[k] for k, *_ in work if results.get(k) is not None]
    all_req_ids = [results.get(k) for k, *_ in work]

    print(f"\nDone. {sum(1 for r in all_req_ids if r is not None)}/{total_batches} batches submitted"
          f"  submit_wall={t_all_submitted - t_start:.2f}s")
    print("\nRequest-ID summary:")
    print_table(
        [{"batch": k, "patch-id": pid, "request-id": results.get(k, "ERROR")}
         for k, pid, _, _ in work],
        ["batch", "patch-id", "request-id"],
    )

    record_deploy(state, ne, base, count, request_ids, patch_ids, kind="deploy", filter_base=filter_base)
    save_state(state)
    print(f"\nState saved to {STATE_FILE}")

    if args.wait and request_ids:
        finish_results = poll_until_done(
            token, request_ids, t_start,
            poll_interval=args.poll_interval,
            timeout=args.poll_timeout,
        )
        _print_timing_summary(
            work, submit_elapsed, results, finish_results,
            t_start, t_all_submitted, args.bulk_window,
        )


def cmd_check(args: argparse.Namespace, token: str, state: dict) -> None:
    if args.all:
        last = last_deploy(state)
        if not last:
            sys.exit("No deploy found in state file. Run deploy first.")
        request_ids = last["request_ids"]
        print(f"Checking {len(request_ids)} request-ids from last deploy (base={last['base']}, count={last['count']}, NE={last['ne']}):\n")
    else:
        request_ids = [args.request_id]

    rows = []
    for rid in request_ids:
        url = f"{restconf_base()}/data/nsp-deployer:deployers/plugin=mdm/deployer={rid}?depth=1"
        eprint(f"GET  {url}")
        st, err = _check_deployer_status(token, rid)
        label = "SUCCESS (not found = deployed)" if st == "SUCCESS" else st
        rows.append({"request-id": rid, "status": label, "error": err})

    print_table(rows, ["request-id", "status", "error"])


def cmd_delete(args: argparse.Namespace, token: str, state: dict) -> None:
    if args.all:
        last = last_deploy(state)
        if not last:
            sys.exit("No deploy found in state file. Run deploy first.")
        request_ids = last["request_ids"]
        print(f"Deleting {len(request_ids)} deployer entries from last deploy:\n")
    else:
        request_ids = [args.request_id]

    for rid in request_ids:
        url = f"{restconf_base()}/data/nsp-deployer:deployers/plugin=mdm/deployer={rid}"
        eprint(f"DELETE {url}")
        status, data = http_request("DELETE", url, bearer_headers(token))
        if status in (200, 204, 404):
            print(f"  request-id={rid}  → HTTP {status} {'(deleted)' if status != 404 else '(not found)'}")
        else:
            print(f"  request-id={rid}  → ERROR HTTP {status}: {data}")


def cmd_list_epipes(args: argparse.Namespace, token: str) -> None:
    ne = args.ne
    if args.service_name:
        # Single epipe lookup by service-name (used as index key)
        url = (
            f"{restconf_base()}/data/network-device-mgr:network-devices"
            f"/network-device={ne}/root/nokia-conf:/configure/service/epipe={args.service_name}?depth=1"
        )
        eprint(f"GET  {url}")
        status, data = http_request("GET", url, bearer_headers(token))
        if status == 404:
            print(f"epipe '{args.service_name}' not found on NE {ne}")
            return
        if status != 200:
            sys.exit(f"list-epipes failed ({status}): {data}")
        print(json.dumps(data, indent=2))
        return

    # Bulk listing — fields=service-id for efficiency when count is high
    url = (
        f"{restconf_base()}/data/network-device-mgr:network-devices"
        f"/network-device={ne}/root/nokia-conf:/configure/service/epipe"
        f"?fields=service-id;service-name;admin-state"
    )
    eprint(f"GET  {url}")
    status, data = http_request("GET", url, bearer_headers(token))
    if status != 200:
        sys.exit(f"list-epipes failed ({status}): {data}")

    epipes: list[dict] = []
    if isinstance(data, dict):
        for key in ("epipe", "nokia-conf:epipe"):
            if key in data:
                val = data[key]
                epipes = val if isinstance(val, list) else [val]
                break

    if not epipes:
        print("No epipes found. Raw response:")
        print(json.dumps(data, indent=2))
        return

    # Optional filter by base range
    if args.base is not None and args.count is not None:
        ids = set(range(args.base, args.base + args.count))
        epipes = [e for e in epipes if isinstance(e, dict) and int(e.get("service-id", -1)) in ids]

    rows = [
        {
            "service-id": e.get("service-id", ""),
            "service-name": e.get("service-name", ""),
            "admin-state": e.get("admin-state", ""),
        }
        for e in epipes
        if isinstance(e, dict)
    ]
    rows.sort(key=lambda r: r["service-id"] if isinstance(r["service-id"], int) else 0)
    print(f"\nEpipes on NE {ne}  (total shown: {len(rows)}):\n")
    print_table(rows, ["service-id", "service-name", "admin-state"])


def cmd_cleanup(args: argparse.Namespace, token: str, state: dict) -> None:
    ne = args.ne

    # Resolve base + filter_base + count from args or last deploy state
    last = last_deploy(state)
    if args.base is not None:
        base = args.base
    elif last:
        base = last["base"]
    else:
        sys.exit("No deploy in state file. Provide --base explicitly.")

    if args.count is not None:
        count = args.count
    elif last:
        count = last["count"]
    else:
        sys.exit("No deploy in state file. Provide --count explicitly.")

    if args.filter_base is not None:
        filter_base = args.filter_base
    elif last and "filter_base" in last:
        filter_base = last["filter_base"]
    else:
        filter_base = base  # fallback: same as service-id base

    batches = gen_cleanup_batches(count)
    total_batches = len(batches)
    print(
        f"\nCleanup {count} epipes + {count} ip-filters on NE {ne}"
        f"  base={base}"
        f"\nBatch plan ({total_batches} request{'s' if total_batches > 1 else ''}): {batches}\n"
    )

    threads = getattr(args, "threads", 5)

    work: list[tuple[int, str, list[dict], str]] = []
    offset = 0
    for k, batch_size in enumerate(batches, start=1):
        ids = list(range(base + offset, base + offset + batch_size))
        patch_id = f"cleanup-{base}-shot{k}"
        edits: list[dict] = []
        for j, sid in enumerate(ids):
            edits.append(epipe_remove(j + 1, sid))
        for j in range(len(ids)):
            fid = filter_base + offset + j
            edits.append(filter_remove(batch_size + j + 1, fid))
        svc_range = f"{svc_name(ids[0])}–{svc_name(ids[-1])}" if len(ids) > 1 else svc_name(ids[0])
        work.append((k, patch_id, edits, svc_range))
        offset += batch_size

    results: dict[int, int | None] = {}
    submit_elapsed: dict[int, float] = {}

    t_start = time.monotonic()

    def _submit(item: tuple[int, str, list[dict], str]) -> tuple[int, int | None]:
        k, patch_id, edits, svc_range = item
        with _print_lock:
            print(f"  Shot {k}/{total_batches}  {svc_range}  ({len(edits)} removes)  patch-id={patch_id}")
        req_id, elapsed = submit_patch(token, ne, patch_id, edits)
        with _print_lock:
            submit_elapsed[k] = elapsed
        return k, req_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(_submit, item) for item in work]
        for fut in concurrent.futures.as_completed(futures):
            k, req_id = fut.result()
            results[k] = req_id

    t_all_submitted = time.monotonic()

    patch_ids = [w[1] for w in work]
    request_ids = [results[k] for k, *_ in work if results.get(k) is not None]

    print(f"\nCleanup done. {sum(1 for r in results.values() if r is not None)}/{total_batches} shots submitted"
          f"  submit_wall={t_all_submitted - t_start:.2f}s")
    if request_ids:
        print("\nCleanup Request-ID summary:")
        print_table(
            [{"shot": k, "patch-id": pid, "request-id": results.get(k, "ERROR")}
             for k, pid, _, _ in work],
            ["shot", "patch-id", "request-id"],
        )
        record_deploy(state, ne, base, count, request_ids, patch_ids, kind="cleanup", filter_base=filter_base)
        save_state(state)
        print(f"\nState saved to {STATE_FILE}")

    if args.wait and request_ids:
        finish_results = poll_until_done(
            token, request_ids, t_start,
            poll_interval=args.poll_interval,
            timeout=args.poll_timeout,
        )
        _print_timing_summary(
            work, submit_elapsed, results, finish_results,
            t_start, t_all_submitted, args.bulk_window,
        )


# ---------------------------------------------------------------------------
# NE cache  (~/.smoke_ne_cache.json)
# Structure: { "<gateway>": { "<ne-id>": {"lag": "lag-2", "sdp": "1", "type": "SR-7750"} } }
# ---------------------------------------------------------------------------

def _cache_key() -> str:
    return os.environ.get("NSP_GATEWAY", "unknown")


def load_ne_cache() -> dict:
    if NE_CACHE_FILE.exists():
        try:
            return json.loads(NE_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_ne_cache(cache: dict) -> None:
    NE_CACHE_FILE.write_text(json.dumps(cache, indent=2))


def get_cached_nes() -> dict[str, dict]:
    """Return NE entries for the current cluster gateway."""
    return load_ne_cache().get(_cache_key(), {})


def _discover_ne(token: str, ne: str) -> tuple[str, str | None, str | None]:
    """Return (ne, first_lag, first_sdp_id<50) for one NE."""
    try:
        url = restconf_base() + f"/data/network-device-mgr:network-devices/network-device={ne}/root/nokia-conf:/configure/lag?depth=1"
        status, data = http_request("GET", url, bearer_headers(token))
        if status != 200:
            return ne, None, None
        lags = data.get("nokia-conf:lag", data.get("lag", []))
        enabled = [l for l in lags if isinstance(l, dict) and l.get("admin-state") == "enable"]
        if not enabled:
            return ne, None, None
        lag_name = enabled[0].get("lag-name") or enabled[0].get("name")

        url2 = restconf_base() + f"/data/network-device-mgr:network-devices/network-device={ne}/root/nokia-conf:/configure/service/sdp?fields=sdp-id;admin-state&depth=1"
        status2, data2 = http_request("GET", url2, bearer_headers(token))
        if status2 != 200:
            return ne, lag_name, None
        sdps = data2.get("nokia-conf:sdp", data2.get("sdp", []))
        enabled_sdps = sorted(
            [d for d in sdps if isinstance(d, dict) and d.get("admin-state") == "enable"],
            key=lambda x: int(str(x.get("sdp-id", 9999))),
        )
        sdp_id = str(enabled_sdps[0]["sdp-id"]) if enabled_sdps else None
        return ne, lag_name, sdp_id
    except Exception:
        return ne, None, None


def cmd_discover(args: argparse.Namespace, token: str) -> None:
    """Discover LAG + SDP for all (or filtered) NEs and cache results."""
    # Resolve NE list
    filter_subnet = args.subnet  # e.g. "9.168." or None
    filter_type   = args.ne_type  # e.g. "SR-7750" or None
    threads       = args.threads

    print(f"Fetching NE list from cluster {_cache_key()} ...")
    url = f"{restconf_base()}/meta/api/v1/nes"
    status, data = http_request("GET", url, bearer_headers(token))
    if status != 200:
        sys.exit(f"list-nes failed ({status}): {data}")

    nes_raw: list[dict] = []
    if isinstance(data, list):
        nes_raw = data
    elif isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                nes_raw = v
                break

    seen: set[str] = set()
    candidates: list[dict] = []
    for ne in nes_raw:
        if not isinstance(ne, dict):
            continue
        ne_id = ne.get("neId") or ne.get("ne-id") or ne.get("id", "")
        ne_type = ne.get("type", "")
        if ne_id in seen:
            continue
        seen.add(ne_id)
        if filter_subnet and not ne_id.startswith(filter_subnet):
            continue
        if filter_type and filter_type.upper() not in ne_type.upper():
            continue
        candidates.append({"ne_id": ne_id, "type": ne_type, "version": ne.get("version", "")})

    print(f"Discovering LAG + SDP for {len(candidates)} NEs (threads={threads}) ...\n")

    discovered: dict[str, dict] = {}
    skipped: list[str] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as pool:
        futures = {pool.submit(_discover_ne, token, c["ne_id"]): c for c in candidates}
        for fut in concurrent.futures.as_completed(futures):
            c = futures[fut]
            ne_id, lag, sdp = fut.result()
            if lag and sdp:
                discovered[ne_id] = {"lag": lag, "sdp": sdp, "type": c["type"], "version": c["version"]}
                print(f"  {ne_id:<20} lag={lag}  sdp={sdp}  ({c['type']} {c['version']})")
            else:
                skipped.append(ne_id)
                print(f"  {ne_id:<20} SKIP (no enabled lag/sdp<50)")

    print(f"\nDiscovered: {len(discovered)}  Skipped: {len(skipped)}")

    # Merge into cache
    cache = load_ne_cache()
    cluster = _cache_key()
    if cluster not in cache:
        cache[cluster] = {}
    cache[cluster].update(discovered)
    save_ne_cache(cache)
    print(f"Cache updated → {NE_CACHE_FILE}  ({len(cache[cluster])} NEs total for {cluster})")


def cmd_show_cache(args: argparse.Namespace) -> None:
    """Display cached NE entries for the current cluster."""
    nes = get_cached_nes()
    if not nes:
        print(f"No cache for cluster {_cache_key()}.  Run: discover")
        return
    subnet = args.subnet
    rows = [
        {"ne-id": ne_id, "lag": v["lag"], "sdp": v["sdp"], "type": v.get("type",""), "version": v.get("version","")}
        for ne_id, v in sorted(nes.items())
        if not subnet or ne_id.startswith(subnet)
    ]
    print(f"\nCached NEs for cluster {_cache_key()}  ({len(rows)} shown):\n")
    print_table(rows, ["ne-id", "lag", "sdp", "type", "version"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="smoke_restconf.py",
        description="NSP RESTCONF smoke tool — epipe + ip-filter via data deployer",
    )
    sub = p.add_subparsers(dest="command", required=True)

    # list-nes
    sub.add_parser("list-nes", help="List all NEs (neId, type, version)")

    # list-lags
    pl = sub.add_parser("list-lags", help="List LAGs on a specific NE")
    pl.add_argument("--ne", required=True, help="NE ID (IP address)")

    # list-sdps
    ps = sub.add_parser("list-sdps", help="List SDPs on a specific NE")
    ps.add_argument("--ne", required=True, help="NE ID (IP address)")

    # deploy
    pd = sub.add_parser("deploy", help="Deploy epipes + ip-filters via YANG PATCH (batched)")
    pd.add_argument("--ne", required=True, help="NE ID (IP address)")
    pd.add_argument("--count", type=int, required=True, help="Number of epipes to create")
    pd.add_argument("--lag", required=True, help="LAG name (e.g. lag-59)")
    pd.add_argument("--sdp", required=True, help="SDP ID (e.g. 2)")
    pd.add_argument("--base", type=int, default=2000, help="Base service-id (default: 2000)")
    pd.add_argument("--filter-base", type=int, default=None, dest="filter_base",
                    help="Base filter-id (default: same as --base; must be 1..65535)")
    pd.add_argument("--vlan-start", type=int, default=1, dest="vlan_start",
                    help="Starting VLAN for SAP sap-id suffix (default: 1, increments per epipe)")
    pd.add_argument("--max-batch", type=int, default=5, dest="max_batch", help="Max epipes per YANG PATCH request (default: 5)")
    pd.add_argument("--threads", type=int, default=5, help="Parallel submission threads (default: 5)")
    pd.add_argument("--wait", action=argparse.BooleanOptionalAction, default=True,
                    help="Poll deployer until done and print timing (default: --wait)")
    pd.add_argument("--poll-interval", type=float, default=2.0, dest="poll_interval",
                    help="Deployer poll interval in seconds (default: 2.0)")
    pd.add_argument("--poll-timeout", type=float, default=120.0, dest="poll_timeout",
                    help="Max seconds to wait for deployer to finish (default: 120)")
    pd.add_argument("--bulk-window", type=float, default=1.0, dest="bulk_window",
                    help="Window in seconds to group finish times for bulk approximation (default: 1.0)")

    # check
    pc = sub.add_parser("check", help="Check deployer status for request-id(s)")
    pcg = pc.add_mutually_exclusive_group(required=True)
    pcg.add_argument("--request-id", type=int, dest="request_id", help="Single request-id")
    pcg.add_argument("--all", action="store_true", help="Check all request-ids from last deploy")

    # delete
    pde = sub.add_parser("delete", help="Delete deployer entry for request-id(s)")
    pdeg = pde.add_mutually_exclusive_group(required=True)
    pdeg.add_argument("--request-id", type=int, dest="request_id", help="Single request-id")
    pdeg.add_argument("--all", action="store_true", help="Delete all request-ids from last deploy")

    # list-epipes
    ple = sub.add_parser("list-epipes", help="Verify created epipes via RESTCONF GET")
    ple.add_argument("--ne", required=True, help="NE ID (IP address)")
    ple.add_argument("--service-name", dest="service_name", default=None,
                     help="Single epipe lookup by service-name (e.g. ep-ag-smoke-113000)")
    ple.add_argument("--base", type=int, default=None,
                     help="Filter to service-ids in [base, base+count) range")
    ple.add_argument("--count", type=int, default=None,
                     help="Used with --base to narrow the listing")

    # cleanup
    pcu = sub.add_parser("cleanup", help="Remove epipes + ip-filters via YANG PATCH (1-2 shots)")
    pcu.add_argument("--ne", required=True, help="NE ID (IP address)")
    pcu.add_argument("--base", type=int, default=None, help="Base service-id (default: from state file)")
    pcu.add_argument("--filter-base", type=int, default=None, dest="filter_base",
                     help="Base filter-id used at creation (default: from state file, else same as --base)")
    pcu.add_argument("--count", type=int, default=None, help="Count (default: from state file)")
    pcu.add_argument("--threads", type=int, default=5, help="Parallel submission threads (default: 5)")
    pcu.add_argument("--wait", action=argparse.BooleanOptionalAction, default=True,
                    help="Poll deployer until done and print timing (default: --wait)")
    pcu.add_argument("--poll-interval", type=float, default=2.0, dest="poll_interval",
                    help="Deployer poll interval in seconds (default: 2.0)")
    pcu.add_argument("--poll-timeout", type=float, default=120.0, dest="poll_timeout",
                    help="Max seconds to wait for deployer to finish (default: 120)")
    pcu.add_argument("--bulk-window", type=float, default=1.0, dest="bulk_window",
                    help="Window in seconds to group finish times for bulk approximation (default: 1.0)")

    # discover
    pdisc = sub.add_parser("discover", help="Discover LAG + SDP for NEs and save to local cache")
    pdisc.add_argument("--subnet", default=None,
                       help="Filter NE IDs by subnet prefix (e.g. '9.168.' or '192.168.96.')")
    pdisc.add_argument("--ne-type", default=None, dest="ne_type",
                       help="Filter by NE type substring (e.g. 'SR-7750')")
    pdisc.add_argument("--threads", type=int, default=10, help="Parallel discovery threads (default: 10)")

    # show-cache
    psc = sub.add_parser("show-cache", help="Show cached NE→LAG+SDP for the current cluster")
    psc.add_argument("--subnet", default=None, help="Filter by NE subnet prefix")

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    state = load_state()
    token = get_token()

    cmd = args.command
    if cmd == "list-nes":
        cmd_list_nes(args, token)
    elif cmd == "list-lags":
        cmd_list_lags(args, token)
    elif cmd == "list-sdps":
        cmd_list_sdps(args, token)
    elif cmd == "deploy":
        cmd_deploy(args, token, state)
    elif cmd == "check":
        cmd_check(args, token, state)
    elif cmd == "delete":
        cmd_delete(args, token, state)
    elif cmd == "list-epipes":
        cmd_list_epipes(args, token)
    elif cmd == "cleanup":
        cmd_cleanup(args, token, state)
    elif cmd == "discover":
        cmd_discover(args, token)
    elif cmd == "show-cache":
        cmd_show_cache(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
