#!/usr/bin/env python3
"""Parse go tool pprof -text output into a simple ranked table."""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)([kKmMgG]?B)?\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%\s+(\S+)\s+(\S+.*)$"
)


def parse(path: Path) -> list[tuple[float, str, str]]:
    rows: list[tuple[float, str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        flat_pct = float(m.group(3))
        sym = m.group(5)
        rest = m.group(6)
        rows.append((flat_pct, sym, rest))
    rows.sort(key=lambda r: r[0], reverse=True)
    return rows


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: alloc_hotspots.py pprof-text.txt", file=sys.stderr)
        return 1
    path = Path(sys.argv[1])
    rows = parse(path)
    print(f"{'flat%':>8}  {'symbol':<40}  location")
    print("-" * 72)
    for flat, sym, rest in rows[:30]:
        print(f"{flat:8.2f}  {sym:<40}  {rest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
