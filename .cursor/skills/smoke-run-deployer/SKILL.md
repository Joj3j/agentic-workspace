# NSP RESTCONF Smoke — Data Deployer (epipe + ip-filter)

## When to apply

- List available NEs on an NSP cluster via RESTCONF
- Discover LAGs and SDPs on a target NE
- Smoke-test the data deployer: create epipes + ip-filters via YANG PATCH
- Drive parallel concurrent submissions to exercise comm-layer-server bulk dispatch
- Track async deployer `request-id` values after submission
- Check deployer status (success = 404 not found)
- Clean up created objects via YANG PATCH remove
- Delete lingering deployer entries

## Cluster-specific variables

The following values **change per cluster** and must be discovered fresh each time:

| Variable | How to obtain |
|----------|---------------|
| `NE_ID` (e.g. `192.168.96.135`) | `list-nes` — pick SROS NEs |
| `--lag` (e.g. `lag-59`) | `list-lags --ne <NE_ID>` — pick a LAG that has free VLANs available for SAP use; each epipe consumes one VLAN on this LAG |
| `--sdp` (e.g. `7`) | `list-sdps --ne <NE_ID>` — pick an operational SDP configured for epipe use; the SDP ID becomes the spoke-sdp bind-id prefix (`{SDP}:{SERVICE_ID}`) |
| `--vlan-start` | Check router-interface SAPs and existing epipe SAPs on the chosen LAG; pick the first free VLAN (e.g. `20` clears `:10` router-interface and any lower in-use VLANs). Error symptom: `MINOR: SVCMGR #1003 sap is already in use` |
| `--base` | Choose a free service-id range not already used on the NE (default `2000`) |
| `--filter-base` | Must stay within `1..65535`; use a separate lower base when `--base` is high |

## Environment setup

Server credentials live in `scripts/smoke-run-deployer/restconf_env.local` (gitignored).

```bash
cd workspace-settings/.cursor/scripts/smoke-run-deployer
cp restconf_env.local.example restconf_env.local
# Edit restconf_env.local: set NSP_GATEWAY, NSP_USER, NSP_PASSWORD

source restconf_env.sh
```

| Variable | Default | Purpose |
|----------|---------|---------|
| `NSP_GATEWAY` | required | NSP VIP host (no scheme, no trailing slash) |
| `NSP_USER` | `admin` | REST Gateway client_credentials user |
| `NSP_PASSWORD` | required | REST Gateway password |
| `NSP_VERIFY_TLS` | `0` | `0` = skip TLS verify (self-signed) |
| `RESTCONF_PORT` | `8545` | RESTCONF API port |

Auth flow: `POST https://{NSP_GATEWAY}/rest-gateway/rest/api/v1/auth/token`
(`grant_type=client_credentials`) → Bearer token used on all RESTCONF calls.

## Cluster change / cache reset

The NE cache (`~/.smoke_ne_cache.json`) is keyed by `NSP_GATEWAY`. When switching clusters:

1. Update `restconf_env.local` with the new `NSP_GATEWAY` IP.
2. Re-source the env: `source restconf_env.sh`
3. Run `discover` to build a fresh cache for the new cluster — the old cluster's cache is preserved under its own key and is not reused.

```bash
# Switch cluster
vi restconf_env.local   # change NSP_GATEWAY
source restconf_env.sh

# Rebuild cache for new cluster
python3 smoke_restconf.py discover --subnet 9.168. --ne-type SR-7750
python3 smoke_restconf.py show-cache
```

## Typical workflow

```bash
source restconf_env.sh

# 1. One-time: discover and cache all NE resources for the cluster
python3 smoke_restconf.py discover --subnet 9.168. --ne-type SR-7750

# 2. Review cache
python3 smoke_restconf.py show-cache

# 3. Deploy (parallel batched YANG PATCH) on a single NE
python3 smoke_restconf.py deploy \
  --ne <NE_ID> --count 10 --lag <LAG> --sdp <SDP> \
  --base 113000 --filter-base 3000 --vlan-start 20

# 4. Verify epipes were created
python3 smoke_restconf.py list-epipes --ne <NE_ID> --base 113000 --count 10

# 5. Check deployer status for all submitted requests
python3 smoke_restconf.py check --all

# 6a. Cleanup objects via YANG PATCH remove
python3 smoke_restconf.py cleanup --ne <NE_ID>

# 6b. Delete any lingering deployer entries
python3 smoke_restconf.py delete --all
```

## All commands and options

### `discover`
Query all NEs in parallel for their first enabled LAG and first SDP (id < 50). Saves
results to `~/.smoke_ne_cache.json` keyed by `NSP_GATEWAY`. Run once per cluster.

```bash
python3 smoke_restconf.py discover \
  [--subnet 9.168.]        \  # filter NE IDs by prefix
  [--ne-type SR-7750]      \  # filter by NE type substring
  [--threads 10]              # parallel discovery threads (default: 10)
```

### `show-cache`
Display the cached NE→LAG+SDP table for the current cluster.

```bash
python3 smoke_restconf.py show-cache [--subnet 9.168.]
```

Cache file: `~/.smoke_ne_cache.json` — keyed by `NSP_GATEWAY`. Changing the gateway in
`restconf_env.local` automatically starts a fresh key; the old cluster's data is retained
under its own key and never reused.

### `list-nes`
List all NEs on the cluster. Output: `neId | type | version`. Deduplicates NE IDs.
```bash
python3 smoke_restconf.py list-nes
```

### `list-lags`
List LAGs on a specific NE.
```bash
python3 smoke_restconf.py list-lags --ne <NE_ID>
```

### `list-sdps`
List SDPs on a specific NE.
```bash
python3 smoke_restconf.py list-sdps --ne <NE_ID>
```

### `deploy`
Create epipes + ip-filters via batched parallel YANG PATCH requests.

```bash
python3 smoke_restconf.py deploy \
  --ne <NE_ID>          \  # required: NE IP address
  --count N             \  # required: number of epipes to create
  --lag <lag-name>      \  # required: LAG name, e.g. lag-59
  --sdp <sdp-id>        \  # required: SDP ID, e.g. 7
  [--base 2000]         \  # base service-id (default: 2000)
  [--filter-base 2000]  \  # base filter-id (default: same as --base; must be 1..65535)
  [--vlan-start 1]      \  # first VLAN for SAP sap-id suffix (default: 1, increments per epipe)
  [--max-batch 5]       \  # max epipes per YANG PATCH request (default: 5)
  [--threads 5]            # parallel submission threads (default: 5)
```

**Parallel submission:** all batches are pre-built and submitted simultaneously via a
`ThreadPoolExecutor(max_workers=--threads)`. This ensures multiple tickets arrive at
comm-layer-server within the same linger window, producing `bulkSize > 1` in the bulk
dispatch log. With sequential submission the linger expires between tickets → `bulkSize=1`.

**VLAN conflict avoidance:** if a SAP VLAN is already in use by a router interface or
another service on the LAG, the deployer will return `MINOR: SVCMGR #1003 sap is already
in use`. Use `list-lags` to check existing SAPs or set `--vlan-start` to a safe range
(e.g. `20`).

### `list-epipes`
Verify created epipes via RESTCONF GET.

```bash
# All epipes on NE
python3 smoke_restconf.py list-epipes --ne <NE_ID>

# Filter to smoke range
python3 smoke_restconf.py list-epipes --ne <NE_ID> --base 113000 --count 10

# Single epipe by name
python3 smoke_restconf.py list-epipes --ne <NE_ID> --service-name epipe113000
```

| Option | Default | Purpose |
|--------|---------|---------|
| `--ne` | required | NE IP address |
| `--base` | — | Filter service-ids to `[base, base+count)` range |
| `--count` | — | Used with `--base` to narrow the listing |
| `--service-name` | — | Single epipe lookup by name (e.g. `epipe2000`) |

### `check`
Check deployer status for one or all request-ids.

```bash
python3 smoke_restconf.py check --request-id <id>
python3 smoke_restconf.py check --all      # all request-ids from last deploy in state file
```

| HTTP | Meaning |
|------|---------|
| 404 Not Found | Deployment succeeded (deployer entry removed) |
| 200 with body | Pending or failed — check `failure-messages` field |

### `delete`
Delete deployer entries.

```bash
python3 smoke_restconf.py delete --request-id <id>
python3 smoke_restconf.py delete --all     # all from last deploy
```

### `cleanup`
Remove epipes + ip-filters via YANG PATCH `remove` (1–2 parallel shots).

```bash
# Use values from state file
python3 smoke_restconf.py cleanup --ne <NE_ID>

# Explicit range
python3 smoke_restconf.py cleanup \
  --ne <NE_ID>          \
  --base 113000         \
  --filter-base 3000    \
  --count 10            \
  [--threads 5]
```

| Option | Default | Purpose |
|--------|---------|---------|
| `--ne` | required | NE IP address |
| `--base` | from state file | Base service-id |
| `--filter-base` | from state file | Base filter-id used at creation |
| `--count` | from state file | Number of epipes to remove |
| `--threads` | `5` | Parallel submission threads |

Cleanup always uses **1 or 2** YANG PATCH requests regardless of count, fired in parallel.

## Deploy batching and numbering

Each YANG PATCH contains a randomly chosen number of epipes in `[2, --max-batch]` with
varying sizes across the run. For `count=10` with `max-batch=5` this produces 2–5 requests.

**Numbering per epipe `i` (0-indexed), `SERVICE_ID = base + i`:**

| Field | Value |
|-------|-------|
| `service-name` | `epipe{SERVICE_ID}` |
| `service-id` | `SERVICE_ID` |
| `sap-id` | `{LAG}:{vlan-start + i}` — increments per epipe |
| `spoke-sdp` bind-id | `{SDP}:{SERVICE_ID}` |
| `filter-name` | `test{filter-base + i}` |
| `filter-id` | `filter-base + i` — must stay within `1..65535` |

## YANG PATCH details

**URL:**
```
PATCH https://{NSP_GATEWAY}:{RESTCONF_PORT}/restconf/data/nsp-network:network/node={neId}/node-root
```

**Headers:**
- `Content-Type: application/yang-patch+json`
- `Accept: application/yang-data+json`
- `Authorization: Bearer <token>`

**GET queries** (without a `fields` parameter) all use `?depth=1`.

## Deployer check / delete URLs

```
GET    https://{NSP_GATEWAY}:{RESTCONF_PORT}/restconf/data/nsp-deployer:deployers/plugin=mdm/deployer={request-id}?depth=1
DELETE https://{NSP_GATEWAY}:{RESTCONF_PORT}/restconf/data/nsp-deployer:deployers/plugin=mdm/deployer={request-id}
```

## State file

`~/.smoke_restconf_state.json` — persists every deploy and cleanup run with timestamps,
NE, base, filter-base, count, and all request-ids. Used automatically by `check --all`,
`delete --all`, and `cleanup` (when `--base` / `--count` are omitted).

## Scripts

| Script | Purpose |
|--------|---------|
| `restconf_env.sh` | Env loader — source before running any script |
| `restconf_env.local` | Local overrides (gitignored) — set `NSP_GATEWAY`, credentials here |
| `restconf_env.local.example` | Template for `restconf_env.local` |
| `smoke_restconf.py` | Main CLI — all subcommands |
