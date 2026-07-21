---
name: nsp-opensearch
description: >-
  NSP OpenSearch log errors: REST Gateway client_credentials token and native HTTPS
  _search bodies for error rollups (Query A/B). Same NSP host for gateway and
  OpenSearch (port 9200 by default). Self-contained in workspace-settings: skill,
  opensearch_env.sh, and nsp_opensearch_log_report.py. Requires credentials or
  networkdata; no other repo dependency.
---

# NSP OpenSearch (token + native `_search`)

**Flow:** (1) **NSP IP / gateway host** — same host for REST Gateway and OpenSearch (see §1). (2) **Bearer token** from the gateway. (3) **POST** `_search` to **`{scheme}://<host>:<opensearch_port>`** (default port **9200**) with that token.

**Canonical location:** This skill and its scripts live only under **`workspace-settings/.cursor/`** (skills + scripts). Treat that tree as the single source of truth.

## Scripts and env (workspace-settings)

| Artifact | Location |
|----------|----------|
| Env loader | `workspace-settings/.cursor/scripts/nsp-opensearch/opensearch_env.sh` |
| Secrets template | `workspace-settings/.cursor/scripts/nsp-opensearch/opensearch_env.local.example` → copy to **`opensearch_env.local`** (gitignored) |
| Log report | `workspace-settings/.cursor/scripts/nsp-opensearch/nsp_opensearch_log_report.py` |

**Agent / user steps:**

```bash
cd workspace-settings/.cursor/scripts/nsp-opensearch
cp opensearch_env.local.example opensearch_env.local
# Edit opensearch_env.local: NSP_GATEWAY, NSP_USER, NSP_PASSWORD
source opensearch_env.sh
python3 nsp_opensearch_log_report.py --minutes 60 --output ~/nsp-log-report.md
```

**CLI highlights:**

| Flag | Purpose |
|------|---------|
| `--minutes N` | UTC lookback (default 60) |
| `--query a` / `b` / `both` | Error rollup (A), level breakdown error rows (B), or both |
| `--samples N` | Append N recent error hits with `LogMessage` snippets |
| `--index NAME` | Single-index `_search` |
| `--auto-widen` | If rollup empty, retry once with **24h** window |
| `--json-out` | Raw JSON from Query A to stdout (debug) |
| `NSP_VERIFY_TLS=0` | Self-signed TLS (set in `opensearch_env.local`) |

---

## 1) Inputs

### Required

- **NSP IP** (`nsp_ip` / **`NSP_GATEWAY`**): **IPv4, IPv6, or DNS name**, optionally with **`:port`** only when the gateway uses a non-default HTTPS port—**without** `https://` (e.g. `100.127.198.155`). Use this value for **both**:
  - **Token:** `https://{nsp_ip}/rest-gateway/rest/api/v1/auth/token` (or with gateway port if embedded in host)
  - **OpenSearch:** `https://{opensearch_host}:{opensearch_port}/_search` where **`opensearch_port`** defaults to **`9200`**
- **NSP username** and **password** for token issuance: **`NSP_USER`** and **`NSP_PASSWORD`** in the environment where commands run, **or** **networkdata**, **or** explicit values in the prompt. **Do not** embed or assume fixed credentials in scripts or skill text.

**Do not** call the token endpoint or OpenSearch until **`nsp_ip`** and credentials are known (prompt, **networkdata**, or env).

### Optional credential bundle

If the user provides a **networkdata JSON path**: read `nspServer.advertisedAddress` → **`nsp_ip`** (same as gateway host); `nspServer.clientUser` / `nspServer.clientPassword` when present (else env **`NSP_USER`** / **`NSP_PASSWORD`**).

### Credential resolution (agents)

Use the **first** source that yields a username **and** password:

1. **Explicit values** in the user message for this request (never log or repeat passwords in chat).
2. **networkdata** JSON (`nspServer.clientUser` / `nspServer.clientPassword`) when a path is given.
3. **Environment variables** `NSP_USER` / `NSP_PASSWORD` on the machine running the commands.

If **none** of the above apply, **do not** guess credentials or hardcode them in command lines. **Prompt** the user to set **`NSP_USER`** / **`NSP_PASSWORD`** (or provide networkdata / explicit values) before calling the token endpoint.

### Optional environment shortcuts

| Variable | Purpose |
|----------|---------|
| `NSP_USER` | REST Gateway `client_credentials` username (**required** for token unless networkdata or explicit prompt supplies it) |
| `NSP_PASSWORD` | REST Gateway password (**required** under the same rule as `NSP_USER`) |
| `NSP_GATEWAY` | Default **`nsp_ip`** when the user does not name the IP in the prompt (no `https://`). **`NSP_IP`** is accepted as an alias when `NSP_GATEWAY` is unset. |
| `NSP_OPENSEARCH_PORT` | Optional OpenSearch TCP port; default **`9200`** if unset |
| `NSP_HTTPS_SCHEME` | **`https`** (default) or **`http`** |
| `NSP_VERIFY_TLS` | **`1`** verify (default); **`0`** for self-signed (matches `curl -k`) |

### Setting `NSP_USER` / `NSP_PASSWORD`

Prefer **`opensearch_env.local`** + **`source opensearch_env.sh`** so a single shell session has credentials without echoing them on the command line.

**Windows PowerShell:**

```powershell
$env:NSP_USER = "<nsp-client-username>"
$env:NSP_PASSWORD = "<nsp-client-password>"
```

**Bash / Git Bash / WSL:**

```bash
export NSP_USER="<nsp-client-username>"
export NSP_PASSWORD="<nsp-client-password>"
```

**Cursor / agent caveat:** a terminal command run **on your behalf** often starts a **new** shell. For agent-driven runs, prefer **sourcing `opensearch_env.sh`** in that same session, or **Windows user** / **system** environment variables for **`NSP_USER`** / **`NSP_PASSWORD`**, or pass **networkdata** / explicit credentials.

### Other optional inputs

- **OpenSearch scheme**: prefer **`https`**; TLS verify off for self-signed via **`NSP_VERIFY_TLS=0`**.
- **Search defaults** (if unspecified): time field **`@datetime`**, window **last 60 minutes** (`gte` / `lte`), aggregation sizes index **100**, app **50**, log_file **20** (override with `--agg-size`).
- **Empty last-hour results:** if Query A returns **`hits.total`: 0** (or empty buckets) for the default 60-minute window, **widen once** (e.g. **24 hours** UTC) before concluding there is no data — or use **`--auto-widen`** on the report script.

## 2) NSP access token (before OpenSearch queries)

OpenSearch in NSP environments typically returns **401** without a **Bearer** token from the REST Gateway.

**Token endpoint** (host = **`nsp_ip`** from §1):

`POST https://{nsp_ip}/rest-gateway/rest/api/v1/auth/token`

| Piece | Value |
|-------|--------|
| Method | `POST` |
| TLS | Self-signed common → **`NSP_VERIFY_TLS=0`** or `curl -k` |
| Header | `Authorization: Basic {Base64 UTF-8 of "username:password"}` |
| Body | `application/x-www-form-urlencoded`: **`grant_type=client_credentials`** |

Parse **`access_token`** → OpenSearch header: `Authorization: Bearer <access_token>`

**Example (bash):** `curl -sk -X POST "https://<nsp_ip>/rest-gateway/rest/api/v1/auth/token" -H "Authorization: Basic <base64_user_colon_pass>" -d "grant_type=client_credentials"`

**Do not** log or paste the full token in chat.

**Windows PowerShell + `curl.exe` (robust pattern):** build `_search` JSON with **`ConvertTo-Json`** (avoid hand-escaping `bool.filter` arrays). JWTs can be long or shell-sensitive: write **`Authorization: Bearer <token>`** to a **one-line temp file** and pass **`curl -H "@<headerfile>"`**. Use **`curl -o <respfile> -w "%{http_code}"`** when you need HTTP status.

## 3) OpenSearch HTTP request

- **`opensearch_host`**: same as **`nsp_ip`** (hostname/IP only; strip `:port` from `nsp_ip` when building OpenSearch URL if the gateway port were ever embedded—typically **`nsp_ip`** is host-only and OpenSearch uses **`NSP_OPENSEARCH_PORT`** or **9200**).
- **`opensearch_port`**: **`9200`** by default, or **`NSP_OPENSEARCH_PORT`** when set.
- **URL (cluster-wide):** `{scheme}://{opensearch_host}:{opensearch_port}/_search`
- **URL (single index):** `{scheme}://{opensearch_host}:{opensearch_port}/<index-name>/_search` when the user names one index (e.g. `nsp-mdm-server-logs-2026.03.26`).
- **Method**: `POST`
- **Headers**: `Content-Type: application/json`; **`Authorization: Bearer <access_token>`** from §2.
- **TLS**: Self-signed → **`NSP_VERIFY_TLS=0`** or `curl -k`.

## 4) Time range filter (required)

Build **UTC** `gte` and `lte` as **now − N minutes** (or hours if the user asks) through **now**, with **milliseconds** and **`Z`** suffix. Range format: **`strict_date_optional_time`**. If the user does not specify a window, use **N = 60** (last **60 minutes**).

## 5) Error log levels (filter)

Error-class `LogLevel.keyword` values:

`ERROR`, `exception`, `Exception`, `Error`, `E`

## 6) Query A — Recommended: error-only rollup (Index × AppName × log_file)

Body template (replace `<GTE>`, `<LTE>`):

```json
{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        {
          "range": {
            "@datetime": {
              "gte": "<GTE>",
              "lte": "<LTE>",
              "format": "strict_date_optional_time"
            }
          }
        },
        {
          "terms": {
            "LogLevel.keyword": [
              "ERROR",
              "exception",
              "Exception",
              "Error",
              "E"
            ]
          }
        }
      ]
    }
  },
  "aggs": {
    "by_index": {
      "terms": { "field": "_index", "size": 100, "order": [{ "_count": "desc" }] },
      "aggs": {
        "by_app": {
          "terms": { "field": "AppName.keyword", "size": 50, "order": [{ "_count": "desc" }] },
          "aggs": {
            "by_log_file": {
              "terms": {
                "field": "log_file.keyword",
                "size": 20,
                "order": [{ "_count": "desc" }],
                "missing": "(no log_file)"
              }
            }
          }
        }
      }
    }
  }
}
```

**Parse**: `aggregations.by_index.buckets` → `by_app` → `by_log_file` → **`doc_count`**. Present **top ~10–15** rows unless the user wants more.

**Optional filters:** `term` on `AppName.keyword`; `bool.must` with `match_phrase` on `LogMessage` (keep range + level `terms` in `filter`).

**Log lines and `LogMessage.keyword`:** stack traces and variable text often make **each** error line a **unique** keyword value, so a **`terms`** agg on `LogMessage.keyword` may show **many buckets with `doc_count`: 1**. For “what are the errors?” prefer **§8 samples** plus a short **thematic summary**, or **`match_phrase` / `wildcard`** filters, rather than relying only on top `LogMessage.keyword` buckets. Fields like **`NeId`** may appear only **inside** `LogMessage` text—if `NeId.keyword` does not exist or buckets are empty, filter with **`query_string`** or **`match`** on `LogMessage` instead.

## 7) Query B — Full level breakdown (Index × AppName × log_file × LogLevel)

**Omit** the `terms` filter on `LogLevel.keyword` from Query A; add **`by_level`** under `by_log_file`:

```json
"by_log_file": {
  "terms": {
    "field": "log_file.keyword",
    "size": 20,
    "order": [{ "_count": "desc" }],
    "missing": "(no log_file)"
  },
  "aggs": {
    "by_level": {
      "terms": { "field": "LogLevel.keyword", "size": 5, "order": [{ "_count": "desc" }] }
    }
  }
}
```

Summarize **only** error-class buckets.

## 8) Optional: sample messages

`POST` with **`size`: 5–20**, **no `aggs`**, same `query` as Query A, `"sort": [{ "@datetime": { "order": "desc", "unmapped_type": "date" } }]`, same **Bearer** header.

## 9) What to return

1. **Window** and aggregation source (Query A / B / samples).
2. **Table**: Query A — Index, AppName, log_file, count; Query B — add LogLevel for error rows.
3. **1–2 example lines** if samples were run.
4. Avoid full JSON unless asked.

## 10) Troubleshooting

- **Cannot connect to OpenSearch**: confirm reachability to **`https://<nsp-ip>:9200`** (or overridden port), firewall, and **HTTPS** vs **HTTP**; try **`NSP_VERIFY_TLS=0`** / `curl -k` for self-signed certs.
- **401 on OpenSearch**: fresh token (§2); **`Authorization: Bearer`** present.
- **401 on token URL**: user/password or wrong **`nsp_ip`** (`advertisedAddress` from networkdata).
- **Connection reset / wrong scheme**: flip `http` ↔ `https`; disable cert verify for self-signed.
- **Empty buckets** or **`hits.total`: 0** with default **60m**: widen time range (try **24h** UTC); increase `terms` `size` on `_index` / `AppName.keyword` / `log_file.keyword`; use **`--auto-widen`** on the report script.
- **OpenSearch `400` / `x_content_parse_exception` on `_search`**: malformed JSON—regenerate the body (e.g. PowerShell **`ConvertTo-Json`**) instead of manual string escaping.
