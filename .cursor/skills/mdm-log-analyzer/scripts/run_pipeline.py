#!/usr/bin/env python3
"""Run parse_mdm_logs.py -> analyze_logs.py -> generate_report.py in one invocation."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="MDM log analyzer: parse, analyze, generate report.")
    ap.add_argument("input", help="Log directory or .log / .log.zip file")
    ap.add_argument(
        "--out-dir",
        default=None,
        help="Output directory for parsed.json, findings.json, report.md, report.html "
        "(default: <skill>/out/report)",
    )
    ap.add_argument("--gc", action="append", default=[], metavar="PATH", help="Optional GC log file (repeatable)")
    ap.add_argument(
        "--threaddump",
        action="append",
        default=[],
        metavar="PATH",
        help="Optional thread dump file (repeatable)",
    )
    args = ap.parse_args()

    script_dir = Path(__file__).resolve().parent
    out_dir = Path(args.out_dir) if args.out_dir else script_dir.parent / "out" / "report"
    out_dir.mkdir(parents=True, exist_ok=True)

    py = sys.executable
    parsed = out_dir / "parsed.json"
    findings = out_dir / "findings.json"
    report_md = out_dir / "report.md"
    report_html = out_dir / "report.html"

    parse_cmd: list[str] = [
        py,
        str(script_dir / "parse_mdm_logs.py"),
        args.input,
        "-o",
        str(parsed),
    ]
    for g in args.gc:
        parse_cmd.extend(["--gc", g])
    for t in args.threaddump:
        parse_cmd.extend(["--threaddump", t])

    subprocess.run(parse_cmd, check=True)
    subprocess.run(
        [py, str(script_dir / "analyze_logs.py"), str(parsed), "-o", str(findings)],
        check=True,
    )
    subprocess.run(
        [
            py,
            str(script_dir / "generate_report.py"),
            str(findings),
            "-o",
            str(report_md),
            "--html",
            str(report_html),
        ],
        check=True,
    )
    print(f"Done. Outputs in {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
