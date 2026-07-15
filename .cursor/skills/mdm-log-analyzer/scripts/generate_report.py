#!/usr/bin/env python3
"""
Generate markdown report and standalone HTML dashboard (Chart.js) from findings.json.
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from urllib.parse import quote
from typing import Any

HOUND_BASE = "http://orbw-web.ca.alcatel-lucent.com:6080/"


def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def build_markdown(data: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# MDM Log Analysis Report")
    lines.append("")
    lines.append(f"- **Generated:** {data.get('generated', '')}")
    summ = data.get("summary", {})
    lines.append(f"- **Total log entries:** {summ.get('total_entries', 'n/a')}")
    lines.append(f"- **Parsed lines:** {summ.get('parsed_lines', 'n/a')}")
    lines.append("")
    lines.append("## Executive summary")
    recs = data.get("recommendations") or []
    if recs:
        for r in recs[:5]:
            lines.append(f"- {r}")
    else:
        lines.append("- No critical automated recommendations; review domain sections.")
    lines.append("")
    lines.append("## Critical / attention areas")
    dom = data.get("domains", {})
    mem = dom.get("memory", {})
    if mem.get("oom_lines"):
        lines.append(f"- **Memory:** OOM lines detected: {mem.get('oom_lines')}")
    stuck = dom.get("stuck_ne", {})
    lines.append(f"- **Resync heuristic:** severity={stuck.get('severity')}, gap={stuck.get('heuristic_gap')}")
    lines.append("")
    lines.append("## Domain findings")
    for name in (
        "adapter",
        "resync",
        "bulk_upload",
        "stuck_ne",
        "thread_pools",
        "memory",
        "zookeeper",
        "gc",
    ):
        block = dom.get(name)
        if not block:
            continue
        lines.append(f"### {name.replace('_', ' ').title()}")
        lines.append("```json")
        lines.append(json.dumps(block, indent=2)[:8000])
        lines.append("```")
        lines.append("")
    lines.append("## Hound code search")
    lines.append("")
    lines.append("| Topic | URL |")
    lines.append("|-------|-----|")
    for term in ("full-resync", "GrpcExecutor", "NodeResyncState", "IBulkUploadManager"):
        qurl = f"{HOUND_BASE}?q={quote(term, safe='')}&i=nope&literal=nope&files=&excludeFiles=&repos="
        lines.append(f"| {term} | {qurl} |")
    lines.append("")
    lines.append("## Graphical analysis")
    lines.append("")
    lines.append("Open the generated **HTML report** in a browser for Chart.js charts.")
    lines.append("")
    lines.append("## Recommendations")
    for i, r in enumerate(recs, 1):
        lines.append(f"{i}. {r}")
    lines.append("")
    return "\n".join(lines)


def build_html(data: dict[str, Any]) -> str:
    charts = data.get("charts") or {}
    rc = charts.get("resync_counts", {})
    tp = charts.get("thread_pool_lines", {})
    mm = charts.get("memory_summary", {})
    gc = charts.get("gc_summary", {})

    def chart_config(cid: str, title: str, labels: list, values: list) -> str:
        labels_j = json.dumps(labels)
        values_j = json.dumps(values)
        return f"""
<div class="card"><h3>{html.escape(title)}</h3><canvas id="{cid}"></canvas></div>
<script>
(function() {{
  const ctx = document.getElementById('{cid}');
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: {labels_j},
      datasets: [{{
        label: '{html.escape(title)}',
        data: {values_j},
        backgroundColor: ['#4477aa','#66aadd','#aa8866','#669966','#9966aa']
      }}]
    }},
    options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
  }});
}})();
</script>"""

    pie_labels = rc.get("labels", []) or ["starts", "dones", "fail_lines"]
    pie_vals = rc.get("values", []) or [0, 0, 0]
    pie_script = ""
    if pie_labels and pie_vals:
        pie_script = f"""
<div class="card"><h3>Resync ratio (starts / dones / fail lines)</h3><canvas id="pie1"></canvas></div>
<script>
(function() {{
  const ctx = document.getElementById('pie1');
  new Chart(ctx, {{
    type: 'pie',
    data: {{
      labels: {json.dumps(pie_labels)},
      datasets: [{{
        data: {json.dumps(pie_vals)},
        backgroundColor: ['#4477aa','#66cc88','#cc6666']
      }}]
    }},
    options: {{ responsive: true }}
  }});
}})();
</script>"""

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>MDM Log Analysis</title>",
        "<script src='https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js'></script>",
        "<style>body{font-family:system-ui,sans-serif;margin:16px;background:#fafafa;} .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;} .card{background:#fff;padding:12px;border-radius:8px;box-shadow:0 1px 3px #0002;} h1{font-size:1.25rem;} h3{margin:0 0 8px 0;font-size:1rem;}</style>",
        "</head><body>",
        f"<h1>MDM Log Analysis</h1><p>Generated: {html.escape(str(data.get('generated','')))}</p>",
        "<div class='grid'>",
    ]

    tp_lab = tp.get("labels", []) or ["mdm-grpc-exec", "sshd-SshClient"]
    tp_val = tp.get("values", []) or [0, 0]
    if len(tp_lab) != len(tp_val):
        tp_val = tp_val + [0] * max(0, len(tp_lab) - len(tp_val))

    mm_lab = mm.get("labels", []) or ["oom_lines", "memory_monitor_lines"]
    mm_val = mm.get("values", []) or [0, 0]
    if len(mm_lab) != len(mm_val):
        mm_val = mm_val + [0] * max(0, len(mm_lab) - len(mm_val))

    gc_lab = gc.get("labels", []) or ["gc_events", "pause_parsed"]
    gc_val = gc.get("values", []) or [0, 0]
    if len(gc_lab) != len(gc_val):
        gc_val = gc_val + [0] * max(0, len(gc_lab) - len(gc_val))

    parts.append(chart_config("c1", "Thread pool keyword hits (log lines)", tp_lab, tp_val))
    parts.append(chart_config("c2", "Memory signals", mm_lab, mm_val))
    parts.append(chart_config("c3", "GC summary", gc_lab, gc_val))
    parts.append("</div>")
    parts.append(pie_script)
    parts.append("<h2>Recommendations</h2><ul>")
    for r in data.get("recommendations") or []:
        parts.append(f"<li>{html.escape(str(r))}</li>")
    parts.append("</ul><h2>Hound</h2><ul>")
    for term in ("full-resync", "GrpcExecutor", "NodeResyncState"):
        q = quote(term, safe="")
        url = f"{HOUND_BASE}?q={q}&i=nope&literal=nope&files=&excludeFiles=&repos="
        parts.append(f"<li><a href=\"{html.escape(url)}\">{html.escape(term)}</a></li>")
    parts.append("</ul></body></html>")
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate MDM analysis reports.")
    ap.add_argument("findings_json", help="Output from analyze_logs.py")
    ap.add_argument("-o", "--output", default="report.md", help="Markdown output path")
    ap.add_argument("--html", default="report.html", help="HTML dashboard output path")
    args = ap.parse_args()

    data = json.loads(Path(args.findings_json).read_text(encoding="utf-8"))
    md = build_markdown(data)
    Path(args.output).write_text(md, encoding="utf-8")
    h = build_html(data)
    Path(args.html).write_text(h, encoding="utf-8")
    print(f"Wrote {args.output} and {args.html}", file=sys.stderr)


if __name__ == "__main__":
    main()
