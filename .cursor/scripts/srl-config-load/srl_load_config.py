#!/usr/bin/env python3
"""srl_load_config.py — Load a flat SR Linux config file onto an SRL NE.

Location: agentic-workspace/.cursor/scripts/srl-config-load/

Always strips NE-specific lines before pushing:
  - system0 interface address  (preserves target NE's own NE ID)
  - mgmt0 static IPv4 address  (each NE has its own management IP)
  - system tls server-profile certificate/key  (IP-bound; not portable)

Applies schema migrations when source and target major versions differ
(e.g. 22.11 → 25.10). For 25.10+ sources, migrations are skipped.

Saves the fixed file + a .meta.json sidecar (NE type, versions, source IP).
With --save-template, copies both to the tools template dir for reuse.

Usage:
    python3 srl_load_config.py \\
        --config /path/to/flat_config.cfg \\
        --ne-ip <TARGET_NE_IP> \\
        --ne-id <NE_ID> \\
        --ne-type 7250-IXR-SRL \\
        --source-ne-ip <SOURCE_NE_IP> \\
        [--source-ver 25.10] [--target-ver 25.10] \\
        [--output-dir /tmp] \\
        [--save-template /home/joji/Go/agentic-workspace/tools/srl-configs] \\
        [--dry-run] [--no-save-startup]

Environment variables (loaded from srl_config_env.local if present):
    SRL_USER        SSH/SCP username               (default: admin)
    SRL_PASSWORD    SSH/SCP password               (default: admin)
    SRL_SOURCE_VER  SRL version config exported from  (default: 25.10)
    SRL_TARGET_VER  SRL version on the target device  (default: 25.10)

Template workflow:
    # 1. Save a clean reusable template (once per source NE):
    python3 srl_load_config.py --config source.cfg \\
        --ne-ip <SOURCE_IP> --ne-id <NE_ID> --ne-type 7250-IXR-SRL \\
        --source-ne-ip <SOURCE_IP> --source-ver 25.10 --target-ver 25.10 \\
        --save-template /home/joji/Go/agentic-workspace/tools/srl-configs \\
        --dry-run

    # 2. Restore the template to any NE of the same type:
    python3 srl_load_config.py \\
        --config /home/joji/Go/agentic-workspace/tools/srl-configs/<stem>_v2510_to_2510_fixed.cfg \\
        --ne-ip <OTHER_NE_IP> --ne-id <OTHER_NE_ID> --ne-type 7250-IXR-SRL \\
        --source-ver 25.10 --target-ver 25.10

After loading, the target NE's gRPC TLS profile has no certificate.
See SKILL.md "After loading: restoring the TLS certificate" for the
step-by-step procedure to generate and deploy an NSP CA-signed cert.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Schema migration functions (legacy sources only — skipped for 25.10+ sources)
# ---------------------------------------------------------------------------

def fix_acl_policer_renames(lines: list[str]) -> list[str]:
    """peak-packet-rate → peak-rate-pps, max-packet-burst → maximum-burst-packet."""
    out = []
    for line in lines:
        line = line.replace("peak-packet-rate", "peak-rate-pps")
        line = line.replace("max-packet-burst", "maximum-burst-packet")
        out.append(line)
    return out


def fix_grpc_server(lines: list[str]) -> list[str]:
    """gnmi-server singleton → grpc-server named list (one instance per network-instance).

    22.11 shape:
        set / system gnmi-server
        set / system gnmi-server admin-state enable
        set / system gnmi-server timeout 7200
        set / system gnmi-server rate-limit 65000
        set / system gnmi-server session-limit 100
        set / system gnmi-server network-instance default
        set / system gnmi-server network-instance default admin-state enable
        set / system gnmi-server network-instance default use-authentication true
        set / system gnmi-server network-instance default port 57400
        set / system gnmi-server network-instance default tls-profile GRPC
        set / system gnmi-server network-instance default source-address [ :: ]
        set / system gnmi-server network-instance mgmt ...

    25.x shape (named list, one NI per instance, use-auth → metadata-authentication):
        set / system grpc-server grpc-default admin-state enable
        set / system grpc-server grpc-default timeout 7200
        set / system grpc-server grpc-default network-instance default
        set / system grpc-server grpc-default port 57400
        ...
        set / system grpc-server mgmt admin-state enable
        set / system grpc-server mgmt network-instance mgmt
        ...
    """
    # First rename gnmi-server → grpc-server everywhere so we work on a
    # uniform token, then do the structural transformation.
    lines = [l.replace("gnmi-server", "grpc-server") for l in lines]

    # Find the contiguous block of grpc-server lines
    start, end = _find_block(lines, "set / system grpc-server")
    if start is None:
        return lines

    block = lines[start:end]

    # Parse shared (top-level) attrs and per-NI attrs
    shared_attrs: dict[str, str] = {}   # attr_name → value suffix (e.g. "7200")
    ni_blocks: dict[str, dict[str, str]] = {}   # ni_name → {attr → value}

    _shared_keys = {"admin-state", "timeout", "rate-limit", "session-limit"}

    for raw in block:
        line = raw.rstrip()
        # "set / system grpc-server"                     → root declaration
        # "set / system grpc-server <attr> <val>"        → shared attr
        # "set / system grpc-server network-instance <ni>" → NI declaration
        # "set / system grpc-server network-instance <ni> <attr> <val>" → NI attr
        m = re.match(r"set / system grpc-server(.*)", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if not rest:
            continue  # bare declaration, skip

        parts = rest.split()
        if parts[0] in _shared_keys:
            shared_attrs[parts[0]] = " ".join(parts[1:]) if len(parts) > 1 else ""
        elif parts[0] == "network-instance" and len(parts) >= 2:
            ni = parts[1]
            if ni not in ni_blocks:
                ni_blocks[ni] = {}
            if len(parts) > 2:
                attr = parts[2]
                val = " ".join(parts[3:])
                # Rename use-authentication → metadata-authentication
                if attr == "use-authentication":
                    attr = "metadata-authentication"
                ni_blocks[ni][attr] = val

    if not ni_blocks:
        # No NI sub-blocks found — just rename and keep as-is
        return lines

    new_block: list[str] = []
    for ni_name, ni_attrs in ni_blocks.items():
        # Use "grpc-default" for the "default" NI instance name to avoid
        # collision with the SRL keyword "default"
        server_name = "grpc-default" if ni_name == "default" else ni_name

        new_block.append(f"set / system grpc-server {server_name}\n")
        for attr, val in shared_attrs.items():
            new_block.append(f"set / system grpc-server {server_name} {attr} {val}\n")
        new_block.append(f"set / system grpc-server {server_name} network-instance {ni_name}\n")
        for attr, val in ni_attrs.items():
            if attr in ("admin-state",):
                continue  # admin-state is at server level (already in shared_attrs)
            suffix = f" {val}" if val else ""
            new_block.append(f"set / system grpc-server {server_name} {attr}{suffix}\n")

    return lines[:start] + new_block + lines[end:]


def fix_ssh_server(lines: list[str]) -> list[str]:
    """ssh-server singleton → named list (one instance per network-instance).

    22.11 shape:
        set / system ssh-server
        set / system ssh-server network-instance default
        set / system ssh-server network-instance default admin-state enable
        set / system ssh-server network-instance default timeout 10
        set / system ssh-server network-instance default rate-limit 20
        set / system ssh-server network-instance mgmt ...

    25.x shape:
        set / system ssh-server ssh-default admin-state enable
        set / system ssh-server ssh-default network-instance default
        set / system ssh-server ssh-default timeout 10
        set / system ssh-server ssh-default rate-limit 20
        set / system ssh-server mgmt admin-state enable
        set / system ssh-server mgmt network-instance mgmt
        ...
    """
    start, end = _find_block(lines, "set / system ssh-server")
    if start is None:
        return lines

    block = lines[start:end]

    ni_blocks: dict[str, dict[str, str]] = {}

    for raw in block:
        line = raw.rstrip()
        m = re.match(r"set / system ssh-server(.*)", line)
        if not m:
            continue
        rest = m.group(1).strip()
        if not rest:
            continue

        parts = rest.split()
        if parts[0] == "network-instance" and len(parts) >= 2:
            ni = parts[1]
            if ni not in ni_blocks:
                ni_blocks[ni] = {}
            if len(parts) > 2:
                ni_blocks[ni][parts[2]] = " ".join(parts[3:])

    if not ni_blocks:
        return lines

    new_block: list[str] = []
    for ni_name, ni_attrs in ni_blocks.items():
        server_name = "ssh-default" if ni_name == "default" else ni_name

        new_block.append(f"set / system ssh-server {server_name}\n")
        admin = ni_attrs.get("admin-state", "enable")
        new_block.append(f"set / system ssh-server {server_name} admin-state {admin}\n")
        new_block.append(f"set / system ssh-server {server_name} network-instance {ni_name}\n")
        for attr, val in ni_attrs.items():
            if attr == "admin-state":
                continue
            suffix = f" {val}" if val else ""
            new_block.append(f"set / system ssh-server {server_name} {attr}{suffix}\n")

    return lines[:start] + new_block + lines[end:]


def fix_snmp_community(lines: list[str]) -> list[str]:
    """Remove old-style 'snmp community <encrypted>' line.

    In 25.x, community is nested under access-group > community-entry.
    The encrypted value from a different device is also non-portable.
    """
    return [l for l in lines if not re.match(r"set / system snmp community ", l)]


def fix_bgp_policy_list_syntax(lines: list[str]) -> list[str]:
    """export-policy / import-policy bare value → wrapped in [ ... ]."""
    out = []
    for line in lines:
        # Match lines where export-policy or import-policy is followed by a
        # bare value (not already a list)
        line = re.sub(
            r"\b(export-policy|import-policy) ([^\[]\S+)$",
            r"\1 [ \2 ]",
            line.rstrip(),
        ) + ("\n" if line.endswith("\n") else "")
        out.append(line)
    return out


def fix_bgp_afi_safi(lines: list[str]) -> list[str]:
    """Insert 'afi-safi' before AFI family names in BGP contexts.

    Covers: group <name>, neighbor <ip>, and top-level bgp.
    Families: ipv4-unicast, ipv6-unicast, evpn, l3vpn-ipv4-unicast, l3vpn-ipv6-unicast.
    """
    afis = r"(ipv4-unicast|ipv6-unicast|evpn|l3vpn-ipv4-unicast|l3vpn-ipv6-unicast)"
    out = []
    for line in lines:
        if "protocols bgp" in line and "afi-safi" not in line:
            new_line = re.sub(
                r"(protocols bgp(?:\s+(?:group|neighbor)\s+\S+)?)\s+" + afis + r"(\s|$)",
                r"\1 afi-safi \2\3",
                line.rstrip(),
            )
            out.append(new_line + "\n" if line.endswith("\n") else new_line)
        else:
            out.append(line)
    return out


def fix_bgp_local_as(lines: list[str]) -> list[str]:
    """local-as <asn> → local-as as-number <asn>."""
    out = []
    for line in lines:
        out.append(re.sub(r"\blocal-as (\d)", r"local-as as-number \1", line))
    return out


def fix_bgp_multipath(lines: list[str]) -> list[str]:
    """multipath max-paths-level-1/2 <N> → multipath ebgp/ibgp maximum-paths <N>."""
    out = []
    for line in lines:
        line = re.sub(r"multipath max-paths-level-1 (\d+)", r"multipath ebgp maximum-paths \1", line)
        line = re.sub(r"multipath max-paths-level-2 (\d+)", r"multipath ibgp maximum-paths \1", line)
        out.append(line)
    return out


def fix_bgp_evpn_rapid_update(lines: list[str]) -> list[str]:
    """Remove 'bgp afi-safi evpn rapid-update' (removed in 25.x)."""
    return [l for l in lines if "afi-safi evpn rapid-update" not in l]


def fix_match_prefix_set(lines: list[str]) -> list[str]:
    """match prefix-set <name> → match prefix prefix-set <name>."""
    out = []
    for line in lines:
        out.append(re.sub(r"\bmatch prefix-set ", "match prefix prefix-set ", line))
    return out


# Map: (source_ver_major, target_ver_major) → ordered list of fix functions
MIGRATIONS: dict[tuple[int, int], list] = {
    (22, 25): [
        fix_acl_policer_renames,
        fix_grpc_server,
        fix_ssh_server,
        fix_snmp_community,
        fix_bgp_policy_list_syntax,
        fix_bgp_afi_safi,
        fix_bgp_local_as,
        fix_bgp_multipath,
        fix_bgp_evpn_rapid_update,
        fix_match_prefix_set,
    ],
}


# ---------------------------------------------------------------------------
# Special-case exclusions
# ---------------------------------------------------------------------------

def strip_system0_address(lines: list[str]) -> list[str]:
    """Remove interface system0 config (preserves NE ID on target device)."""
    return [l for l in lines if not re.match(r"set / interface system0\b", l)]


def strip_mgmt0_ipv4_address(lines: list[str]) -> list[str]:
    """Remove static mgmt0 IPv4 address (each NE has its own management IP)."""
    return [l for l in lines if not re.match(r"set / interface mgmt0 subinterface 0 ipv4 address ", l)]


def strip_tls_cert_and_key(lines: list[str]) -> list[str]:
    """Remove TLS certificate and key material from system tls server-profiles.

    Certificates embed the source NE's management IP in the SAN and are not
    portable. Stripping them lets NSP MDM re-provision the correct cert for
    the target NE, or allows manual cert restoration via the NSP PKI server.

    Lines removed (pattern):
        set / system tls server-profile <name> certificate <pem>
        set / system tls server-profile <name> key <encrypted>

    Other tls server-profile attributes (e.g. authenticate-client) are kept.
    """
    return [
        l for l in lines
        if not re.match(r"set / system tls server-profile \S+ (certificate|key) ", l)
    ]


# ---------------------------------------------------------------------------
# Template metadata helpers
# ---------------------------------------------------------------------------

def load_meta(cfg_path: Path) -> dict:
    """Load .meta.json sidecar for a fixed config file, or return {}."""
    meta_path = cfg_path.with_suffix(".meta.json")
    if meta_path.exists():
        try:
            return json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_meta(cfg_path: Path, meta: dict) -> None:
    """Write .meta.json sidecar alongside a fixed config file."""
    meta_path = cfg_path.with_suffix(".meta.json")
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"Metadata saved   → {meta_path}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_block(lines: list[str], prefix: str) -> tuple[int | None, int]:
    """Return (start, end) indices of a contiguous block matching prefix."""
    start = None
    end = 0
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            if start is None:
                start = i
            end = i + 1
        elif start is not None and not line.startswith(prefix):
            break
    return start, end


def _ver_major(ver: str) -> int:
    """Return the major version number from a string like '22.11' or '25.10'."""
    return int(ver.split(".")[0])


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a subprocess command, streaming output, and return result."""
    result = subprocess.run(cmd, check=check)
    return result


def scp_file(src: str, ne_ip: str, dest_path: str, user: str, password: str) -> None:
    """SCP a file to the target NE."""
    cmd = [
        "sshpass", "-p", password,
        "scp",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        src,
        f"{user}@{ne_ip}:{dest_path}",
    ]
    print(f"[scp] {src} → {user}@{ne_ip}:{dest_path}")
    run(cmd)


def ssh_commands(ne_ip: str, user: str, password: str, commands: list[str]) -> subprocess.CompletedProcess:
    """Run a sequence of SRL CLI commands over SSH (stdin heredoc)."""
    stdin_data = "\n".join(commands) + "\n"
    cmd = [
        "sshpass", "-p", password,
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"{user}@{ne_ip}",
    ]
    print(f"[ssh] {user}@{ne_ip} → {commands}")
    result = subprocess.run(cmd, input=stdin_data.encode(), capture_output=False, check=False)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Load a flat SR Linux config onto an NE with version migration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--config", required=True,
                   help="Path to local flat config file (set statements)")
    p.add_argument("--ne-ip", required=True,
                   help="Target NE management IP")
    p.add_argument("--user", default=os.environ.get("SRL_USER", "admin"),
                   help="SSH/SCP username (default: admin or $SRL_USER)")
    p.add_argument("--password", default=os.environ.get("SRL_PASSWORD", "admin"),
                   help="SSH/SCP password (default: admin or $SRL_PASSWORD)")
    p.add_argument("--source-ver", default=os.environ.get("SRL_SOURCE_VER", "25.10"),
                   help="SRL version config was exported from (default: 25.10)")
    p.add_argument("--target-ver", default=os.environ.get("SRL_TARGET_VER", "25.10"),
                   help="SRL version on target device (default: 25.10)")
    p.add_argument("--ne-id",
                   help="Target NE ID (system0 loopback — always stripped from source "
                        "config to preserve the target NE's own NE ID)")
    p.add_argument("--ne-type",
                   help="NE hardware type (e.g. 7250-IXR-SRL). Stored in metadata and "
                        "used to warn when restoring to a different NE type.")
    p.add_argument("--keep-mgmt0-ip", action="store_true",
                   help="Apply mgmt0 static IP from source config (default: skip it)")
    p.add_argument("--output-dir", default=None,
                   help="Directory to save fixed config file (default: same as source)")
    p.add_argument("--source-ne-ip",
                   help="IP of the NE the config was exported from (recorded in metadata)")
    p.add_argument("--save-template", metavar="TOOLS_DIR", default=None,
                   help="Also copy the fixed config + metadata to TOOLS_DIR for reuse "
                        "(e.g. ../tools/srl-configs). Use --ne-type to record NE type.")
    p.add_argument("--dry-run", action="store_true",
                   help="Apply fixes and save file, but do not push to device")
    p.add_argument("--no-save-startup", action="store_true",
                   help="Skip 'save startup' after commit")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"Error: config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    src_major = _ver_major(args.source_ver)
    tgt_major = _ver_major(args.target_ver)
    migration_key = (src_major, tgt_major)

    # Load source file
    lines = config_path.read_text(encoding="utf-8").splitlines(keepends=True)
    print(f"Loaded {len(lines)} lines from {config_path}")

    # Apply migrations
    fixes = MIGRATIONS.get(migration_key)
    if fixes:
        print(f"Applying {len(fixes)} migration fix(es): "
              f"SRL {args.source_ver} → SRL {args.target_ver}")
        for fix_fn in fixes:
            before = len(lines)
            lines = fix_fn(lines)
            after = len(lines)
            delta = f" ({after - before:+d} lines)" if after != before else ""
            print(f"  [{fix_fn.__name__}]{delta}")
    elif src_major == tgt_major:
        print(f"Same major version ({args.source_ver}), no migration needed.")
    else:
        print(f"Warning: no migration defined for {args.source_ver} → {args.target_ver}. "
              "Loading as-is.")

    # Check for NE-type mismatch against an existing template's metadata
    source_meta = load_meta(config_path)
    if source_meta.get("ne_type") and args.ne_type:
        if source_meta["ne_type"] != args.ne_type:
            print(
                f"\n⚠  WARNING: NE type mismatch!\n"
                f"   Template NE type : {source_meta['ne_type']}\n"
                f"   Target NE type   : {args.ne_type}\n"
                f"   Config was created for a different hardware platform. "
                f"Some settings (interfaces, cards, etc.) may not apply.\n",
                file=sys.stderr,
            )

    # Apply special-case exclusions (all unconditional)
    before = len(lines)
    lines = strip_system0_address(lines)
    delta = before - len(lines)
    ne_id_hint = f" (target NE ID: {args.ne_id})" if args.ne_id else ""
    if delta:
        print(f"  [strip_system0_address] removed {delta} line(s) — "
              f"preserving target NE's own NE ID{ne_id_hint}")

    if not args.keep_mgmt0_ip:
        before = len(lines)
        lines = strip_mgmt0_ipv4_address(lines)
        delta = before - len(lines)
        if delta:
            print(f"  [strip_mgmt0_ipv4_address] removed static mgmt0 IP "
                  f"({delta} line(s) removed)")

    before = len(lines)
    lines = strip_tls_cert_and_key(lines)
    delta = before - len(lines)
    if delta:
        print(f"  [strip_tls_cert_and_key] removed {delta} TLS cert/key line(s) "
              f"(NSP must re-provision cert for target NE after load)")

    # Save fixed file
    out_dir = Path(args.output_dir) if args.output_dir else config_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = config_path.stem
    out_name = f"{stem}_v{args.source_ver.replace('.', '')}_to_{args.target_ver.replace('.', '')}_fixed.cfg"
    out_path = out_dir / out_name
    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"Fixed config saved → {out_path} ({len(lines)} lines)")

    # Save metadata sidecar
    meta = {
        "ne_type":      args.ne_type or source_meta.get("ne_type", ""),
        "source_ver":   args.source_ver,
        "target_ver":   args.target_ver,
        "source_ne_ip": args.source_ne_ip or source_meta.get("source_ne_ip", ""),
        "created_at":   datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    save_meta(out_path, meta)

    # Optionally copy fixed config + metadata to a tools/template directory
    if args.save_template:
        tpl_dir = Path(args.save_template).expanduser().resolve()
        tpl_dir.mkdir(parents=True, exist_ok=True)
        tpl_cfg  = tpl_dir / out_path.name
        tpl_meta = tpl_cfg.with_suffix(".meta.json")
        tpl_cfg.write_text("".join(lines), encoding="utf-8")
        save_meta(tpl_cfg, meta)
        print(f"Template saved   → {tpl_cfg}")
        print(f"                   {tpl_meta}")

    if args.dry_run:
        print("Dry-run mode: stopping here (not pushing to device).")
        return

    # SCP to device
    remote_path = f"/home/{args.user}/{out_path.name}"
    scp_file(str(out_path), args.ne_ip, remote_path, args.user, args.password)

    # SSH: discard any stale candidate, source config, (optionally) save startup
    cli_cmds = [
        "enter candidate",
        "discard stay",
        f"source {remote_path} auto-commit",
    ]
    if not args.no_save_startup:
        cli_cmds.append("save startup")

    result = ssh_commands(args.ne_ip, args.user, args.password, cli_cmds)
    if result.returncode != 0:
        print(f"\nError: SSH session exited with code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)

    print("\nDone.")


if __name__ == "__main__":
    main()
