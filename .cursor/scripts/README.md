# Scripts (under .cursor)

Scripts used with the workspace: SRL config load, Confluence, NSP OpenSearch log reports, etc.
Skills live in `.cursor/skills/`.

## SRL: load flat config onto an NE

See [`srl-config-load/README.md`](srl-config-load/README.md).

Scripts: `srl-config-load/` — `srl_load_config.py`, `srl_config_env.sh`.
Templates: `tools/srl-configs/` — fixed configs + `.meta.json` sidecars.
Skill: `.cursor/skills/srl-config-load/SKILL.md`.

## K8s test clients

See [`k8s-test-client/`](k8s-test-client/) for scripts. Skill: `.cursor/skills/k8s-test-client/SKILL.md`.

```bash
cd workspace-settings/.cursor/scripts/k8s-test-client
cp k8s_test_env.local.example k8s_test_env.local   # first time only
# Edit k8s_test_env.local: jump host IP, SSH user/key
source k8s_test_env.sh

bash k8s_run_test_client.sh --status --client comm-layer-server
bash k8s_run_test_client.sh --client comm-layer-server
bash k8s_run_test_client.sh --client device-registry
bash k8s_run_test_client.sh --client comm-worker-gnmi
```

## Go repo: CI-parity delta coverage

See [`build-go-repo/`](build-go-repo/) for scripts. Skill: `.cursor/skills/build-go-repo/SKILL.md`.

```bash
# From any .go-make repo root (e.g. comm-worker-gnmi-go):
bash workspace-settings/.cursor/scripts/build-go-repo/delta_coverage_check.sh
```

Uses `BUILDER=docker make test` + `build-unittest-coverage-delta:1` — matches Jenkins (not host `gocover-cobertura`).

## NSP OpenSearch: error log reports

See [`nsp-opensearch/`](nsp-opensearch/) for scripts. Skill: `.cursor/skills/nsp-opensearch/SKILL.md`.

```bash
cd workspace-settings/.cursor/scripts/nsp-opensearch
cp opensearch_env.local.example opensearch_env.local   # first time only
# Edit: NSP_GATEWAY, NSP_USER, NSP_PASSWORD (optional: NSP_OPENSEARCH_PORT, NSP_VERIFY_TLS=0)
source opensearch_env.sh

python3 nsp_opensearch_log_report.py --minutes 60 --output /tmp/nsp-logs.md
python3 nsp_opensearch_log_report.py --query both --samples 5 --auto-widen -o /tmp/nsp-logs.md
python3 nsp_opensearch_log_report.py --index 'nsp-example-logs-2026.04.10' --json-out
```

## Confluence: read / create pages

See [`confluence/`](confluence/) for scripts.

| Skill | Use for |
|-------|---------|
| `.cursor/skills/confluence-read/SKILL.md` | **Read-only** (summarize, fetch HTML/text by title or page ID) |
| `.cursor/skills/confluence-page/SKILL.md` | **Read + create**; authoring rules; `confluence_create_page.py` |

Both use the same `confluence_env.sh` / `confluence_env.local` in `confluence/`.

```bash
cd workspace-settings/.cursor/scripts/confluence
cp confluence_env.local.example confluence_env.local   # first time only
# Edit confluence_env.local: CONFLUENCE_BASE_URL, CONFLUENCE_USERNAME, CONFLUENCE_API_TOKEN
source confluence_env.sh

# Read by title
python3 confluence_read_page.py --title "MDC Wrapper Server" --space-key NSPArchEvo

# Read by page ID
python3 confluence_read_page.py --page-id 123456789

# Create under a parent title
python3 confluence_create_page.py \
  --parent-title "MDC Wrapper Server" --space-key NSPArchEvo \
  --title "Your New Page Title" --body "<p>Content.</p>"

# Create from an HTML body file
python3 confluence_create_page.py \
  --parent-id 2069174542 --title "Device Registry Arch" \
  --body-file <repo>/docs/confluence/body.html
```
