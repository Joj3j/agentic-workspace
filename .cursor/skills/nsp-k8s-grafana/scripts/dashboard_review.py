#!/usr/bin/env python3
"""
Dashboard review tool — analyzes a Grafana dashboard JSON for counter quality,
consistency, and best practices. Works offline (no server needed).

Usage:
  python dashboard_review.py <dashboard.json> [--fix] [--output fixed.json]
    --fix       Auto-fix known issues and write corrected JSON
    --output    Output path for fixed JSON (default: <input>-fixed.json)
"""

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict


def load_dashboard(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("dashboard", data), data


def iter_panels(dash):
    """Yield (panel, row_title) for every leaf panel."""
    for p in dash.get("panels", []):
        if p.get("type") == "row":
            for sub in p.get("panels", []):
                yield sub, p.get("title", "")
        else:
            yield p, ""


def extract_targets(panel):
    """Yield (expr, refId, legendFormat) from a panel."""
    for t in panel.get("targets", []):
        expr = t.get("expr", "")
        if expr:
            yield expr, t.get("refId", "?"), t.get("legendFormat", "")


def metric_names(expr):
    """Extract base metric names from PromQL (ignoring functions)."""
    funcs = {"sum", "rate", "avg", "min", "max", "count", "topk", "bottomk",
             "histogram_quantile", "increase", "irate", "delta", "deriv",
             "absent", "clamp", "round", "sort", "vector", "scalar",
             "label_replace", "label_join", "on", "by", "without",
             "ignoring", "group_left", "group_right", "clamp_max", "clamp_min",
             "sort_desc", "abs", "ceil", "floor", "exp", "ln", "log2", "log10", "sqrt"}
    names = re.findall(r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*[\{\[]', expr)
    return [n for n in names if n.lower() not in funcs]


class ReviewResult:
    def __init__(self):
        self.warnings = []
        self.errors = []
        self.info = []
        self.fixes_applied = []

    def warn(self, pid, title, msg):
        self.warnings.append(f"Panel {pid} '{title}': {msg}")

    def error(self, pid, title, msg):
        self.errors.append(f"Panel {pid} '{title}': {msg}")

    def fixed(self, pid, title, msg):
        self.fixes_applied.append(f"Panel {pid} '{title}': {msg}")

    def summary(self):
        print(f"\n{'=' * 90}")
        print(f"Review Summary:  {len(self.errors)} errors  |  {len(self.warnings)} warnings  |  {len(self.info)} info")
        if self.fixes_applied:
            print(f"  Auto-fixed: {len(self.fixes_applied)}")
        print(f"{'=' * 90}")
        for e in self.errors:
            print(f"  ERROR:   {e}")
        for w in self.warnings:
            print(f"  WARN:    {w}")
        for i in self.info:
            print(f"  INFO:    {i}")
        if self.fixes_applied:
            print(f"\n  --- Fixes Applied ---")
            for f in self.fixes_applied:
                print(f"  FIX:     {f}")


def review_dashboard(dash, fix=False):
    result = ReviewResult()
    all_metrics = Counter()
    all_exprs = []
    panel_types = Counter()
    rows = []

    for panel, row_title in iter_panels(dash):
        pid = panel.get("id", "?")
        title = panel.get("title", "Untitled")
        ptype = panel.get("type", "unknown")
        panel_types[ptype] += 1

        # Check for deprecated panel types
        if ptype == "graph":
            result.warn(pid, title, f"Uses deprecated 'graph' panel type — migrate to 'timeseries'")
            if fix:
                panel["type"] = "timeseries"
                result.fixed(pid, title, "Changed type 'graph' -> 'timeseries'")

        # Check field config
        fc = panel.get("fieldConfig", {}).get("defaults", {})
        if not fc.get("unit") and ptype in ("timeseries", "graph", "gauge", "stat"):
            result.warn(pid, title, "No unit set — values will show raw numbers")

        for expr, ref_id, legend in extract_targets(panel):
            all_exprs.append((pid, title, expr, ref_id, legend))

            # Whitespace
            if expr != expr.strip():
                result.warn(pid, title, f"Ref {ref_id}: leading/trailing whitespace in expr")
                if fix:
                    for t in panel.get("targets", []):
                        if t.get("refId") == ref_id:
                            t["expr"] = expr.strip()
                    result.fixed(pid, title, f"Ref {ref_id}: trimmed whitespace")

            # Hardcoded pod ordinals
            hardcoded = re.findall(r'pod="([^"]*-\d+)"', expr)
            if hardcoded and "$instance" not in expr:
                result.warn(pid, title,
                    f"Ref {ref_id}: hardcoded pod name '{hardcoded[0]}' — use $instance variable for flexibility")
                if fix:
                    for hc in hardcoded:
                        base = re.sub(r'-\d+$', '', hc)
                        new_expr = expr.replace(f'pod="{hc}"', f'pod=~"{base}-$instance"')
                        for t in panel.get("targets", []):
                            if t.get("refId") == ref_id:
                                t["expr"] = new_expr
                        expr = new_expr
                    result.fixed(pid, title, f"Ref {ref_id}: replaced hardcoded pod with $instance")

            # Inconsistent $instance vs $instance$ (regex end anchor)
            if "$instance$" in expr and "$instance}" in expr:
                result.warn(pid, title, f"Ref {ref_id}: mixed $instance$ and $instance in same expr")

            # Missing rate() on counter metrics
            for m in metric_names(expr):
                all_metrics[m] += 1
                if m.endswith("_total") and "rate(" not in expr and "increase(" not in expr:
                    result.warn(pid, title,
                        f"Ref {ref_id}: metric '{m}' is a counter (_total) but no rate()/increase()")

            # Empty legendFormat
            if not legend or legend == "{{}}":
                result.warn(pid, title, f"Ref {ref_id}: empty or default legendFormat — graph legends will be unhelpful")

        # Check threshold config
        thresholds = fc.get("thresholds", {}).get("steps", [])
        if len(thresholds) >= 2 and thresholds[-1].get("value") == 80:
            result.info.append(f"Panel {pid} '{title}': uses default threshold 80 — consider tuning for this metric")

    # Dashboard-level checks
    templating = dash.get("templating", {}).get("list", [])
    if not templating:
        result.warn("N/A", "Dashboard", "No template variables defined — dashboard is not parameterized")

    result.info.append(f"Total panels: {sum(panel_types.values())} ({dict(panel_types)})")
    result.info.append(f"Unique metrics used: {len(all_metrics)}")
    result.info.append(f"Total PromQL expressions: {len(all_exprs)}")

    # Duplicate expressions
    expr_counter = Counter(e for _, _, e, _, _ in all_exprs)
    dupes = {e: c for e, c in expr_counter.items() if c > 1}
    if dupes:
        result.info.append(f"Duplicate expressions: {len(dupes)} (used across multiple panels)")

    return result


def main():
    parser = argparse.ArgumentParser(description="Review Grafana dashboard JSON for quality issues")
    parser.add_argument("dashboard", help="Dashboard JSON file path")
    parser.add_argument("--fix", action="store_true", help="Auto-fix known issues")
    parser.add_argument("--output", "-o", help="Output path for fixed JSON")
    args = parser.parse_args()

    dash, full_data = load_dashboard(args.dashboard)
    title = dash.get("title", "Unknown")
    uid = dash.get("uid", "N/A")

    print(f"Dashboard: {title}")
    print(f"UID:       {uid}")
    print(f"Panels:    {sum(1 for _ in iter_panels(dash))}")

    result = review_dashboard(dash, fix=args.fix)
    result.summary()

    if args.fix and result.fixes_applied:
        out = args.output or args.dashboard.replace(".json", "-fixed.json")
        if "dashboard" in full_data:
            full_data["dashboard"] = dash
        else:
            full_data = dash
        with open(out, "w", encoding="utf-8") as f:
            json.dump(full_data, f, indent=2, ensure_ascii=False)
        print(f"\nFixed dashboard written to: {out}")
        print(f"  Import with: python grafana_api.py dashboards import {out} --overwrite")


if __name__ == "__main__":
    main()
