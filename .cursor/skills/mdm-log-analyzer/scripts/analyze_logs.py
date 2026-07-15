#!/usr/bin/env python3
"""
Analyze parsed MDM log JSON (from parse_mdm_logs.py) and emit findings + chart data.
Domain modules: adapter, resync, bulk_upload, stuck_ne, thread_pools, memory, zookeeper, gc.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

HOUND_BASE = "http://orbw-web.ca.alcatel-lucent.com:6080/"


def hound_link(term: str) -> str:
    from urllib.parse import quote

    q = quote(term, safe="")
    return f"{HOUND_BASE}?q={q}&i=nope&literal=nope&files=&excludeFiles=&repos="


def load_parsed(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_messages(data: dict[str, Any]) -> List[dict[str, Any]]:
    return data.get("entries", [])


# --- Domain: adapter ---
def analyze_adapter(entries: List[dict[str, Any]]) -> dict[str, Any]:
    keys = (
        "AdapterTaskExecutor",
        "IRequestAdapter",
        "BundleException",
        "ServiceUnavailable",
        "Unable to start",
    )
    hits: List[dict[str, Any]] = []
    for e in entries:
        msg = (e.get("message") or "") + " " + (e.get("raw") or "")
        if not any(k in msg for k in keys):
            continue
        lvl = e.get("level") or ""
        if any(x in msg for x in ("BundleException", "ServiceUnavailable", "Unable to start")):
            sev = "high"
        else:
            sev = "medium"
        hits.append(
            {
                "severity": sev,
                "excerpt": (e.get("raw") or "")[:500],
                "source_file": e.get("source_file"),
                "line_no": e.get("line_no"),
            }
        )
    return {
        "keyword_hits": len(hits),
        "samples": hits[:20],
        "hound": hound_link("AdapterTaskExecutor"),
    }


# --- Domain: resync ---
RE_NE = re.compile(r"\b(?:ne|NE|node)[\s:=]+([A-Za-z0-9_.:-]+)", re.I)
RE_UUID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I
)


def analyze_resync(entries: List[dict[str, Any]]) -> dict[str, Any]:
    start_kw = ("fullResyncStarted", "full-resync", "fullResync", "FullResync")
    done_kw = ("fullResyncDone", "full resync done", "fullResyncDone")
    fail_kw = ("resync", "Resync")  # narrowed below

    starts: List[dict[str, Any]] = []
    dones: List[dict[str, Any]] = []
    fails: List[dict[str, Any]] = []

    for e in entries:
        raw = e.get("raw") or ""
        msg = (e.get("message") or "") + raw
        low = msg.lower()
        if any(s in msg for s in start_kw) or "fullresyncstarted" in low:
            ne = None
            m = RE_NE.search(msg)
            if m:
                ne = m.group(1)
            elif RE_UUID.search(msg):
                ne = RE_UUID.search(msg).group(0)
            starts.append({"ne": ne, "raw": raw[:400], "source": e.get("source_file")})
        if any(d in msg for d in done_kw):
            dones.append({"raw": raw[:400]})
        if "fail" in low and "resync" in low:
            fails.append({"raw": raw[:400]})

    fail_n = len(fails)
    return {
        "starts_count": len(starts),
        "dones_count": len(dones),
        "fail_lines": fail_n,
        "starts_sample": starts[:15],
        "fails_sample": fails[:15],
        "hound": hound_link("NodeResyncState"),
    }


def analyze_stuck_ne(resync: dict[str, Any]) -> dict[str, Any]:
    """Heuristic: many starts vs dones => possible stuck; NE-specific pairing needs richer parsing."""
    s, d = resync.get("starts_count", 0), resync.get("dones_count", 0)
    gap = max(0, s - d)
    severity = "low"
    if s > 10 and gap > s * 0.3:
        severity = "medium"
    if s > 50 and gap > s * 0.5:
        severity = "high"
    return {
        "heuristic_gap": gap,
        "severity": severity,
        "note": "Pair NE id from log lines for precise stuck NE list; see resync starts_sample.",
        "hound": hound_link("RegisteredNe"),
    }


# --- Domain: bulk upload ---
def analyze_bulk(entries: List[dict[str, Any]]) -> dict[str, Any]:
    keys = ("BulkUpload", "bulk upload", "performBulkUpload", "IBulkUpload", "TriggerBulkUpload")
    hits: List[str] = []
    for e in entries:
        msg = (e.get("message") or "") + (e.get("raw") or "")
        if any(k.lower() in msg.lower() for k in keys):
            hits.append((e.get("raw") or "")[:400])
    return {
        "hits": len(hits),
        "samples": hits[:20],
        "hound": hound_link("IBulkUploadManager"),
    }


# --- Domain: thread pools ---
def analyze_thread_pools(entries: List[dict[str, Any]]) -> dict[str, Any]:
    prefixes = ("mdm-grpc-exec", "sshd-SshClient", "grpc-default-executor")
    counts = Counter()
    for e in entries:
        t = e.get("thread") or ""
        for p in prefixes:
            if p in t or p in (e.get("raw") or ""):
                counts[p] += 1
    return {
        "keyword_line_counts": dict(counts),
        "hound_grpc": hound_link("GrpcExecutor"),
    }


# --- Domain: memory ---
def analyze_memory(entries: List[dict[str, Any]]) -> dict[str, Any]:
    keys = ("MemoryMonitorPrintTimer", "MemoryMonitor", "OutOfMemoryError", "heap")
    oom = 0
    mon = 0
    samples: List[str] = []
    for e in entries:
        raw = e.get("raw") or ""
        if "OutOfMemoryError" in raw:
            oom += 1
            samples.append(raw[:500])
        if "MemoryMonitor" in raw or "MemoryMonitorPrintTimer" in (e.get("thread") or ""):
            mon += 1
    severity = "critical" if oom else ("medium" if mon > 0 else "low")
    return {"oom_lines": oom, "memory_monitor_lines": mon, "severity": severity, "samples": samples[:10]}


# --- Domain: zookeeper ---
def analyze_zookeeper(entries: List[dict[str, Any]]) -> dict[str, Any]:
    zhits = 0
    samples: List[str] = []
    for e in entries:
        raw = e.get("raw") or ""
        thread = e.get("thread") or ""
        if "connection-event-worker" in thread or "connection-event-worker" in raw:
            zhits += 1
        if any(
            x in raw for x in ("KeeperException", "Session expired", "Connection loss", "zookeeper")
        ):
            zhits += 1
            samples.append(raw[:400])
    return {"related_lines": zhits, "samples": samples[:15]}


# --- Domain: GC (from embedded gc_events or log lines) ---
def analyze_gc(data: dict[str, Any], entries: List[dict[str, Any]]) -> dict[str, Any]:
    gc_events = data.get("gc_events") or []
    pauses = [g for g in gc_events if g.get("pause_ms") is not None]
    worst = max((g.get("pause_ms") or 0) for g in pauses) if pauses else None
    # Fallback: scan log lines
    gc_lines = 0
    for e in entries:
        r = e.get("raw") or ""
        if "GC(" in r or "Pause Young" in r or "Pause Full" in r:
            gc_lines += 1
    return {
        "parsed_gc_events": len(gc_events),
        "pause_samples": len(pauses),
        "worst_pause_ms": worst,
        "gc_like_lines_in_app_log": gc_lines,
    }


def build_charts(
    resync: dict[str, Any],
    thread_pools: dict[str, Any],
    memory: dict[str, Any],
    gc: dict[str, Any],
) -> dict[str, Any]:
    return {
        "resync_counts": {
            "labels": ["starts", "dones", "fail_lines"],
            "values": [
                resync.get("starts_count", 0),
                resync.get("dones_count", 0),
                resync.get("fail_lines", 0),
            ],
        },
        "thread_pool_lines": {
            "labels": list(thread_pools.get("keyword_line_counts", {}).keys()) or ["mdm-grpc-exec", "sshd-SshClient"],
            "values": list(thread_pools.get("keyword_line_counts", {}).values())
            if thread_pools.get("keyword_line_counts")
            else [0, 0],
        },
        "memory_summary": {
            "labels": ["oom_lines", "memory_monitor_lines"],
            "values": [memory.get("oom_lines", 0), memory.get("memory_monitor_lines", 0)],
        },
        "gc_summary": {
            "labels": ["gc_events", "pause_parsed"],
            "values": [gc.get("parsed_gc_events", 0), gc.get("pause_samples", 0)],
        },
    }


def run_all(data: dict[str, Any]) -> dict[str, Any]:
    entries = iter_messages(data)
    resync = analyze_resync(entries)

    findings: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "total_entries": len(entries),
            "parsed_lines": sum(1 for e in entries if e.get("parsed")),
        },
        "domains": {
            "adapter": analyze_adapter(entries),
            "resync": resync,
            "stuck_ne": analyze_stuck_ne(resync),
            "bulk_upload": analyze_bulk(entries),
            "thread_pools": analyze_thread_pools(entries),
            "memory": analyze_memory(entries),
            "zookeeper": analyze_zookeeper(entries),
            "gc": analyze_gc(data, entries),
        },
        "thread_dumps": data.get("thread_dumps"),
        "charts": {},
        "recommendations": [],
    }

    findings["charts"] = build_charts(
        findings["domains"]["resync"],
        findings["domains"]["thread_pools"],
        findings["domains"]["memory"],
        findings["domains"]["gc"],
    )

    # Simple recommendations
    recs: List[str] = []
    if findings["domains"]["memory"].get("oom_lines", 0) > 0:
        recs.append("Investigate heap and GC; capture GC logs and thread dump at OOM.")
    if findings["domains"]["resync"].get("fail_lines", 0) > 5:
        recs.append("Review resync failures; correlate NE IDs and Hound NodeResyncState paths.")
    if findings["domains"]["stuck_ne"].get("severity") in ("high", "medium"):
        recs.append("High resync start/done gap; verify stuck NEs and connectivity (SSH/NETCONF).")
    if findings["domains"]["zookeeper"].get("related_lines", 0) > 20:
        recs.append("ZooKeeper noise detected; check session stability and cluster health.")
    findings["recommendations"] = recs

    return findings


def main() -> None:
    ap = argparse.ArgumentParser(description="Analyze parsed MDM JSON.")
    ap.add_argument("parsed_json", help="Output from parse_mdm_logs.py")
    ap.add_argument("-o", "--output", default="-", help="Findings JSON (default stdout)")
    args = ap.parse_args()

    data = load_parsed(Path(args.parsed_json))
    out = run_all(data)
    s = json.dumps(out, indent=2)
    if args.output == "-":
        sys.stdout.write(s)
    else:
        Path(args.output).write_text(s, encoding="utf-8")


if __name__ == "__main__":
    main()
