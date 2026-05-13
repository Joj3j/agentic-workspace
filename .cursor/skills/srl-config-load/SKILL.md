---
name: srl-config-load
description: >-
  Load a flat SR Linux config file (set statements, as produced by 'info flat')
  onto an SRL NE via SSH CLI. Preserves the target NE's NE ID (system0) and
  mgmt0 IP, strips TLS cert/key material, saves the fixed file with version
  info and a metadata sidecar for reuse, then sources it on the device with
  auto-commit and save startup. Base config version is 25.10+; schema
  migrations are available for older sources (e.g. 22.11). Use when the user
  wants to restore or load a flat SRL config onto any NE of the same type, or
  reuse a previously saved template from tools/srl-configs/.
---

# SRL Config Load

Load a flat SR Linux config file onto an NE with automatic schema migration.

## Prerequisites

- `sshpass` — required for SSH/SCP to the NE. Install if missing:
  ```bash
  sudo apt-get install sshpass
  ```
- SSH/SCP access to the target NE.
- A flat config file: `set / ...` statements (produced by `info flat` or
  `save file running-config.txt text from running` on an SRL device).

## Scripts and env (workspace-settings)

| Artifact | Location |
|----------|----------|
| Main script | `.cursor/scripts/srl-config-load/srl_load_config.py` |
| Env loader | `.cursor/scripts/srl-config-load/srl_config_env.sh` |
| Secrets template | `.cursor/scripts/srl-config-load/srl_config_env.local.example` → copy to `srl_config_env.local` (gitignored) |
| Saved templates | `tools/srl-configs/` — reusable fixed configs + `.meta.json` sidecars |

## Agent steps

### 1 — Set up env (once)

```bash
cd workspace-settings/.cursor/scripts/srl-config-load
cp srl_config_env.local.example srl_config_env.local
# Edit: SRL_USER, SRL_PASSWORD, SRL_SOURCE_VER, SRL_TARGET_VER
source srl_config_env.sh
```

### 2 — Check for an existing template

Before exporting a raw config, check if a clean template already exists in
`tools/srl-configs/`. Each template has a `.meta.json` sidecar:

```json
{
  "ne_type":      "7250-IXR-SRL",
  "source_ver":   "25.10",
  "target_ver":   "25.10+",
  "source_ne_ip": "100.127.201.116",
  "created_at":   "2026-05-05T18:58:39Z"
}
```

If a matching template exists for the target NE type, skip straight to step 4.
The script warns if `--ne-type` differs from the template's recorded `ne_type`.

### 3 — Dry-run: inspect and save the fixed file

```bash
cd workspace-settings/.cursor/scripts/srl-config-load
python3 srl_load_config.py \
    --config /path/to/flat_config.cfg \
    --ne-ip <TARGET_NE_IP> \
    --ne-id <NE_ID> \
    --ne-type 7250-IXR-SRL \
    --source-ne-ip <SOURCE_NE_IP> \
    --source-ver 25.10 \
    --target-ver 25.10 \
    --save-template /home/joji/Go/workspace-settings/tools/srl-configs \
    --dry-run
```

With `--save-template`, the fixed config and its `.meta.json` are copied to
`tools/srl-configs/` for future reuse on any NE of the same type.

Inspect the fixed file before pushing. Reuse it for multiple NEs of the same
version without re-running the migration.

### 4 — Load onto the NE

```bash
cd workspace-settings/.cursor/scripts/srl-config-load
python3 srl_load_config.py \
    --config /path/to/flat_config.cfg \
    --ne-ip <TARGET_NE_IP> \
    --ne-id <NE_ID> \
    --ne-type 7250-IXR-SRL
```

Or, reusing a saved template from `tools/srl-configs/`:

```bash
cd workspace-settings/.cursor/scripts/srl-config-load
python3 srl_load_config.py \
    --config /home/joji/Go/workspace-settings/tools/srl-configs/<stem>_v2510_to_2510_fixed.cfg \
    --ne-ip <OTHER_NE_IP> \
    --ne-id <OTHER_NE_ID> \
    --ne-type 7250-IXR-SRL \
    --source-ver 25.10 \
    --target-ver 25.10
```

The script reads the template's `.meta.json` and warns if `--ne-type` does not
match the recorded type:

```
⚠  WARNING: NE type mismatch!
   Template NE type : 7250-IXR-SRL
   Target NE type   : 7730-SXR-SRL
   Config was created for a different hardware platform. Some settings may not apply.
```

### What the script does internally

1. Loads the flat config file and reads `.meta.json` sidecar (if present).
2. Warns if `--ne-type` differs from the template's recorded NE type.
3. Applies version-specific schema migrations (if source and target major
   versions differ).
4. **Always** strips `system0` interface lines — preserves the target NE's
   NE ID (system0 loopback is the NSP-managed NE identifier; never portable).
5. Strips `mgmt0` static IPv4 address — each NE has its own management IP.
6. Strips `system tls server-profile <name> certificate/key` lines — TLS
   certificates embed the source NE's management IP in the SAN and are not
   portable. The target NE needs its own NSP CA-signed cert (see below).
7. Saves fixed file as `<stem>_v<src>_to_<tgt>_fixed.cfg` + `.meta.json`.
8. With `--save-template`, copies both to the tools template dir.
9. SCPs fixed file to `/home/<user>/` on the target NE.
10. SSHs into the SRL CLI:
    - `enter candidate`
    - `discard stay` (clears any stale candidate)
    - `source <remote_file> auto-commit`
    - `save startup`

## After loading: restoring the TLS certificate

After a config load, the target NE's gRPC server TLS profile will have no
certificate or key. NSP gNMI worker connections will fail with:

```
transport: authentication handshake failed: tls: failed to verify certificate:
x509: certificate is valid for <old_ip>, not <target_ip>
```

To restore a valid NSP CA-signed certificate for the target NE:

```bash
# 1. Extract NSP Development Root CA key from the NSP PKI server pod
kubectl exec -n nsp-psa-restricted nsp-pki-server-... -- \
    cat /opt/nsp/tools/ca-external/tls.key > /tmp/pki_ca.key
kubectl exec -n nsp-psa-restricted nsp-pki-server-... -- \
    cat /opt/nsp/tools/ca-external/tls.crt > /tmp/pki_ca.crt

# 2. Generate new key + CSR for target NE
openssl genrsa -out /tmp/ne.key 2048
openssl req -new -key /tmp/ne.key \
  -subj "/C=DE/ST=HE/L=Frankfurt/O=IPD/OU=PLM/CN=ne-<NE_ID>/emailAddress=nobody@nokia.com" \
  -out /tmp/ne.csr
printf "subjectAltName = IP:<TARGET_NE_MGMT_IP>\nextendedKeyUsage = serverAuth, clientAuth\nkeyUsage = digitalSignature, keyEncipherment\n" > /tmp/ne.ext

# 3. Sign with NSP CA
openssl x509 -req -in /tmp/ne.csr -CA /tmp/pki_ca.crt -CAkey /tmp/pki_ca.key \
  -CAcreateserial -days 3650 -extfile /tmp/ne.ext -out /tmp/ne.crt

# 4. Build SRL config snippet
CERT=$(cat /tmp/ne.crt); KEY=$(cat /tmp/ne.key)
printf 'set / system tls server-profile tls-profile-1 certificate "%s"\n' "$CERT" > /tmp/cert_restore.cfg
printf 'set / system tls server-profile tls-profile-1 key "%s"\n' "$KEY" >> /tmp/cert_restore.cfg
echo 'set / system tls server-profile tls-profile-1 authenticate-client false' >> /tmp/cert_restore.cfg
echo 'set / system grpc-server mgmt tls-profile tls-profile-1' >> /tmp/cert_restore.cfg

# 5. SCP + source on NE, then bounce grpc-server mgmt
sshpass -p admin scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  /tmp/cert_restore.cfg admin@<TARGET_NE_IP>:/home/admin/cert_restore.cfg
printf 'enter candidate\ndiscard stay\nsource /home/admin/cert_restore.cfg auto-commit\nsave startup\n' \
  | sshpass -p admin ssh -T -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    admin@<TARGET_NE_IP>

printf 'enter candidate\nset / system grpc-server mgmt admin-state disable\ncommit now\nenter candidate\nset / system grpc-server mgmt admin-state enable\ncommit now\nsave startup\n' \
  | sshpass -p admin ssh -T -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    admin@<TARGET_NE_IP>

# 6. Verify
echo | openssl s_client -connect <TARGET_NE_IP>:57400 -showcerts 2>/dev/null \
  | openssl x509 -noout -subject -issuer -ext subjectAltName
```

## Schema migrations (legacy sources only)

Only needed when `--source-ver` major version differs from `--target-ver`.
For 25.10+ sources these are skipped automatically.

| Fix | Description |
|-----|-------------|
| `fix_grpc_server` | `gnmi-server` singleton → `grpc-server` named list; `use-authentication` → `metadata-authentication` |
| `fix_ssh_server` | `ssh-server` singleton → named list |
| `fix_acl_policer_renames` | `peak-packet-rate` → `peak-rate-pps`, `max-packet-burst` → `maximum-burst-packet` |
| `fix_snmp_community` | Removes non-portable encrypted SNMP community |
| `fix_bgp_policy_list_syntax` | Wraps bare `export-policy`/`import-policy` in `[ ... ]` |
| `fix_bgp_afi_safi` | Inserts `afi-safi` before AFI family names |
| `fix_bgp_local_as` | `local-as <asn>` → `local-as as-number <asn>` |
| `fix_bgp_multipath` | `max-paths-level-1/2` → `ebgp/ibgp maximum-paths` |
| `fix_bgp_evpn_rapid_update` | Removes `evpn rapid-update` (removed in 25.x) |
| `fix_match_prefix_set` | `match prefix-set <name>` → `match prefix prefix-set <name>` |

To add a new fix: write `def fix_<name>(lines) -> list[str]` in
`srl_load_config.py` and register it in the `MIGRATIONS` dict.

## Troubleshooting

- **`sshpass` not found**: install with `sudo apt-get install sshpass` before
  running any script commands.
- **`source` errors (Unknown token)**: a YANG path was renamed in the target
  SRL version. Identify the failing line, look up the correct path on the
  target NE with `info flat / <path>`, then either fix the source file directly
  or add a new migration fix function and re-run with `--dry-run`.
- **Commit fails (leafref / conflict)**: a referenced object (prefix-set,
  policy, interface) doesn't exist on the target. Remove or correct the
  offending lines in the fixed config and retry.
- **gNMI TLS failure after load**: expected — TLS cert/key are stripped.
  Follow the "Restoring the TLS certificate" section above.
- **NE type mismatch warning**: review the fixed config for hardware-specific
  sections (cards, MDAs, port types) that may not apply to the target NE.
