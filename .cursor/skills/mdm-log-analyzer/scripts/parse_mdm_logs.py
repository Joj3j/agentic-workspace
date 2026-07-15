#!/usr/bin/env python3
"""
Parse MDM Java logs (log4j-style), optional GC snippets, and thread dumps into JSON.
Handles plain .log files and .log.zip archives; walks directories.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

# log4j test pattern: %-4r [%t] %-5p %c %x - %m%n
RE_REL_LINE = re.compile(
    r"^(?P<rel>\d+)\s+\[(?P<thread>[^\]]*)\]\s+(?P<level>\S+)\s+(?P<logger>\S+)\s+"
    r"(?P<rest>.*?)\s*-\s*(?P<message>.*)$"
)
# ISO-like: 2026-03-23 14:30:00,123 or 2026-03-23T14:30:00.123
RE_ISO_LINE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}[.,]\d+)\s+"
    r"\[(?P<thread>[^\]]*)\]\s+(?P<level>\S+)\s+(?P<logger>\S+)\s+"
    r"(?P<rest>.*?)\s*-\s*(?P<message>.*)$"
)
RE_SERVER = re.compile(r"\b(mdm-server-\d+)\b", re.I)
RE_THREAD_DUMP_HEADER = re.compile(r'^"([^"]+)"\s+#(\d+)')
RE_JAVA_THREAD_STATE = re.compile(r"^\s*java\.lang\.Thread\.State:\s*(\w+)")

# GC heuristic lines (HotSpot -Xlog / legacy)
RE_GC_PAUSE = re.compile(r"Pause\s+(Young|Full|Mixed|Native)", re.I)
RE_GC_MS = re.compile(r"(\d+\.?\d*)\s*ms")


@dataclass
class LogEntry:
    source_file: str
    source_date: Optional[str]
    line_no: int
    raw: str
    parsed: bool
    rel_ms: Optional[int]
    iso_ts: Optional[str]
    thread: Optional[str]
    level: Optional[str]
    logger: Optional[str]
    message: Optional[str]
    server_hint: Optional[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def infer_source_date(path: Path) -> Optional[str]:
    """From MdmServer.2026-03-23.0.log.zip or parent dir YYYY-MM-DD."""
    m = re.search(r"MdmServer\.(\d{4}-\d{2}-\d{2})", path.name)
    if m:
        return m.group(1)
    parent = path.parent.name
    if re.match(r"^\d{4}-\d{2}-\d{2}$", parent):
        return parent
    return None


def iter_log_paths(root: Path) -> Generator[Path, None, None]:
    for dirpath, _, files in os.walk(root):
        for f in files:
            p = Path(dirpath) / f
            if f.endswith(".log") or f.endswith(".log.zip"):
                yield p


def read_lines_from_zip(zpath: Path) -> Generator[tuple[str, int, str], None, None]:
    with zipfile.ZipFile(zpath, "r") as zf:
        for name in zf.namelist():
            if name.endswith("/") or not name.lower().endswith(".log"):
                continue
            with zf.open(name) as fh:
                text = io.TextIOWrapper(fh, encoding="utf-8", errors="replace")
                for i, line in enumerate(text, 1):
                    yield name, i, line.rstrip("\n\r")


def read_lines_from_file(path: Path) -> Generator[tuple[str, int, str], None, None]:
    with path.open(encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            yield path.name, i, line.rstrip("\n\r")


def parse_log_line(line: str) -> tuple[bool, dict[str, Any]]:
    m = RE_ISO_LINE.match(line)
    if m:
        d = m.groupdict()
        return True, {
            "rel_ms": None,
            "iso_ts": d["ts"].replace("T", " "),
            "thread": d["thread"].strip(),
            "level": d["level"],
            "logger": d["logger"],
            "message": d["message"],
        }
    m = RE_REL_LINE.match(line)
    if m:
        d = m.groupdict()
        return True, {
            "rel_ms": int(d["rel"]),
            "iso_ts": None,
            "thread": d["thread"].strip(),
            "level": d["level"],
            "logger": d["logger"],
            "message": d["message"],
        }
    return False, {}


def extract_server_hint(line: str) -> Optional[str]:
    m = RE_SERVER.search(line)
    return m.group(1) if m else None


def parse_file(path: Path) -> list[LogEntry]:
    entries: list[LogEntry] = []
    src_date = infer_source_date(path)

    if path.suffix.lower() == ".zip":
        for inner_name, line_no, raw in read_lines_from_zip(path):
            ok, fields = parse_log_line(raw)
            hint = extract_server_hint(raw)
            entries.append(
                LogEntry(
                    source_file=f"{path.as_posix()}::{inner_name}",
                    source_date=src_date,
                    line_no=line_no,
                    raw=raw,
                    parsed=ok,
                    rel_ms=fields.get("rel_ms"),
                    iso_ts=fields.get("iso_ts"),
                    thread=fields.get("thread"),
                    level=fields.get("level"),
                    logger=fields.get("logger"),
                    message=fields.get("message"),
                    server_hint=hint,
                )
            )
    else:
        for _, line_no, raw in read_lines_from_file(path):
            ok, fields = parse_log_line(raw)
            hint = extract_server_hint(raw)
            entries.append(
                LogEntry(
                    source_file=path.as_posix(),
                    source_date=src_date,
                    line_no=line_no,
                    raw=raw,
                    parsed=ok,
                    rel_ms=fields.get("rel_ms"),
                    iso_ts=fields.get("iso_ts"),
                    thread=fields.get("thread"),
                    level=fields.get("level"),
                    logger=fields.get("logger"),
                    message=fields.get("message"),
                    server_hint=hint,
                )
            )
    return entries


def parse_gc_file(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f, 1):
            if RE_GC_PAUSE.search(line) or "GC(" in line or "GarbageCollection" in line:
                ms = None
                mm = RE_GC_MS.search(line)
                if mm:
                    try:
                        ms = float(mm.group(1))
                    except ValueError:
                        pass
                out.append(
                    {
                        "source_file": path.as_posix(),
                        "line_no": i,
                        "raw": line.rstrip("\n\r"),
                        "pause_ms": ms,
                    }
                )
    return out


def parse_thread_dump(path: Path) -> dict[str, Any]:
    threads: list[dict[str, Any]] = []
    current: Optional[dict[str, Any]] = None
    with path.open(encoding="utf-8", errors="replace") as f:
        for line in f:
            m = RE_THREAD_DUMP_HEADER.match(line)
            if m:
                if current:
                    threads.append(current)
                current = {"name": m.group(1), "id": int(m.group(2)), "state": None, "lines": []}
                continue
            if current is not None:
                sm = RE_JAVA_THREAD_STATE.match(line)
                if sm:
                    current["state"] = sm.group(1)
                current["lines"].append(line.rstrip("\n\r"))
        if current:
            threads.append(current)
    blocked = sum(1 for t in threads if t.get("state") == "BLOCKED")
    return {
        "source_file": path.as_posix(),
        "thread_count": len(threads),
        "blocked_count": blocked,
        "threads_sample": threads[:50],
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse MDM logs to JSON.")
    ap.add_argument("input", help="File or directory containing MdmServer.log / *.zip")
    ap.add_argument("-o", "--output", default="-", help="Output JSON file (default stdout)")
    ap.add_argument(
        "--gc",
        action="append",
        default=[],
        metavar="PATH",
        help="Optional GC log file(s) to include under gc_events",
    )
    ap.add_argument(
        "--threaddump",
        action="append",
        default=[],
        metavar="PATH",
        help="Optional thread dump file(s)",
    )
    args = ap.parse_args()

    root = Path(args.input)
    all_entries: list[LogEntry] = []

    if root.is_file():
        if root.suffix.lower() in (".log", ".zip"):
            all_entries.extend(parse_file(root))
    else:
        for p in sorted(iter_log_paths(root)):
            all_entries.extend(parse_file(p))

    payload: dict[str, Any] = {
        "generated": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "entry_count": len(all_entries),
        "entries": [e.to_dict() for e in all_entries],
    }

    gc_events: list[dict[str, Any]] = []
    for g in args.gc:
        gc_events.extend(parse_gc_file(Path(g)))
    if gc_events:
        payload["gc_events"] = gc_events

    dumps: list[dict[str, Any]] = []
    for t in args.threaddump:
        dumps.append(parse_thread_dump(Path(t)))
    if dumps:
        payload["thread_dumps"] = dumps

    out_s = json.dumps(payload, indent=2)
    if args.output == "-":
        sys.stdout.write(out_s)
    else:
        Path(args.output).write_text(out_s, encoding="utf-8")


if __name__ == "__main__":
    main()
