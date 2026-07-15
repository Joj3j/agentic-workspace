#!/usr/bin/env python3
"""
Cleanup epipes + ip-filters across all cached SROS NEs in the 9.168.* subnet.

Usage (after sourcing restconf_env.sh):
  python3 multi_ne_cleanup.py [--count N] [--base B] [--filter-base F]
                               [--threads T] [--poll-interval P]
                               [--poll-timeout S] [--bulk-window W]
                               [--subnet SUBNET]
"""
from __future__ import annotations
import argparse, concurrent.futures, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import smoke_restconf as s


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-NE cleanup (epipe + ip-filter)")
    p.add_argument("--count",         type=int,   default=10,       help="Epipes per NE (default: 10)")
    p.add_argument("--base",          type=int,   default=113000,   help="Base service-id (default: 113000)")
    p.add_argument("--filter-base",   type=int,   default=3000,     dest="filter_base",
                   help="Base filter-id (default: 3000)")
    p.add_argument("--max-batch",     type=int,   default=50,       dest="max_batch",
                   help="Max epipes per YANG PATCH remove (default: 50; auto-used when count > 1)")
    p.add_argument("--threads",       type=int,   default=20,       help="Parallel threads (default: 20)")
    p.add_argument("--poll-interval", type=float, default=5.0,      dest="poll_interval")
    p.add_argument("--poll-timeout",  type=float, default=1800.0,   dest="poll_timeout",
                   help="Max seconds to wait for deployer (default: 1800)")
    p.add_argument("--poll-workers",  type=int,   default=20,       dest="poll_workers",
                   help="Parallel HTTP workers for deployer polling (default: 50)")
    p.add_argument("--bulk-window",   type=float, default=1.0,      dest="bulk_window")
    p.add_argument("--subnet",        default="9.168.",
                   help="Filter NE IDs by subnet prefix (default: 9.168.)")
    return p


def main() -> None:
    args = build_parser().parse_args()
    token = s.get_token()

    cache = json.loads((Path.home() / ".smoke_ne_cache.json").read_text())
    gw_nes: dict[str, dict] = cache.get(s._cache_key(), {})
    nes = {ne: cfg for ne, cfg in gw_nes.items() if ne.startswith(args.subnet)}
    if not nes:
        sys.exit(f"No cached NEs matching subnet '{args.subnet}' for cluster {s._cache_key()}")

    COUNT     = args.count
    BASE      = args.base
    FBASE     = args.filter_base
    MAX_BATCH = args.max_batch

    print(f"Cleanup {COUNT} epipes + {COUNT} ip-filters on {len(nes)} NEs")
    print(f"base={BASE}  filter-base={FBASE}  max-batch={MAX_BATCH}  threads={args.threads}\n")

    all_work: list[tuple[str, int, int, str, list, str]] = []
    for ne in sorted(nes):
        # For large counts use gen_deploy_batches to keep edit blocks within deployer limits;
        # for small counts (≤2) use the simple 1-2 shot cleanup.
        batches = s.gen_deploy_batches(COUNT, MAX_BATCH) if COUNT > 2 else s.gen_cleanup_batches(COUNT)
        offset = 0
        for k, bsz in enumerate(batches, start=1):
            ids = list(range(BASE + offset, BASE + offset + bsz))
            patch_id = f"cleanup-{ne}-s{k}"
            edits: list = []
            for j, sid in enumerate(ids):
                edits.append(s.epipe_remove(j+1, sid))
            for j in range(bsz):
                edits.append(s.filter_remove(bsz + j + 1, FBASE + offset + j))
            svc_rng = (f"{s.svc_name(ids[0])}–{s.svc_name(ids[-1])}"
                       if bsz > 1 else s.svc_name(ids[0]))
            all_work.append((ne, k, len(batches), patch_id, edits, svc_rng))
            offset += bsz

    print(f"Total PATCH requests: {len(all_work)}\n")

    results: dict[tuple, int | None] = {}
    ne_req_ids: dict[str, list[int]] = {}
    ne_first_submit_ts: dict[str, float] = {}
    t_start = time.monotonic()

    def _submit(item):
        ne, k, total_k, patch_id, edits, svc_rng = item
        req_id, elapsed = s.submit_patch(token, ne, patch_id, edits)
        t_now = time.monotonic()
        with s._print_lock:
            print(f"  {ne:<20} shot {k}/{total_k}  {svc_rng:<40}  req={req_id}  {elapsed:.0f}ms")
            ne_first_submit_ts.setdefault(ne, t_now)
        return ne, k, req_id

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.threads) as pool:
        futures = [pool.submit(_submit, item) for item in all_work]
        for fut in concurrent.futures.as_completed(futures):
            ne, k, req_id = fut.result()
            results[(ne, k)] = req_id
            if req_id is not None:
                ne_req_ids.setdefault(ne, []).append(req_id)

    t_all_submitted = time.monotonic()
    ok = sum(1 for r in results.values() if r is not None)
    print(f"\n{ok}/{len(all_work)} cleanup patches submitted  submit_wall={t_all_submitted - t_start:.2f}s")

    all_req_ids = [r for r in results.values() if r is not None]
    finish_results = s.poll_until_done(
        token, all_req_ids, t_start,
        poll_interval=args.poll_interval,
        timeout=args.poll_timeout,
        poll_workers=args.poll_workers,
    )

    t_last = max((r["finish_ts"] for r in finish_results.values()), default=t_all_submitted)
    total_wall = t_last - t_start

    ok_nes = sum(
        1 for ne, rids in ne_req_ids.items()
        if all(finish_results.get(r, {}).get("status") == "SUCCESS" for r in rids)
    )
    print(f"\nPer-NE cleanup results — {ok_nes}/{len(ne_req_ids)} NEs fully successful:")
    s.print_ne_timing_table(ne_req_ids, finish_results, ne_first_submit_ts)

    print(f"\nTotal: submit_wall={t_all_submitted - t_start:.2f}s  total_wall={total_wall:.2f}s")
    bulk_msg = s.format_bulk_summary(
        [r["finish_ts"] for r in finish_results.values()], window_s=args.bulk_window)
    if bulk_msg:
        print(f"Bulk approximation: {bulk_msg}")


if __name__ == "__main__":
    main()
