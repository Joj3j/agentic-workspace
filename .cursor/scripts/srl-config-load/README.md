# SRL: load flat config onto an NE

Load a flat SR Linux config file (`set /` statements) onto an SRL NE. Reusable
clean templates are saved in `tools/srl-configs/` (each with a `.meta.json`
sidecar tracking NE type and version).

## Prerequisites (once)

```bash
sudo apt-get install -y sshpass
```

## Set env (once)

```bash
cd workspace-settings/.cursor/scripts/srl-config-load
cp srl_config_env.local.example srl_config_env.local
# Edit srl_config_env.local: SRL_USER, SRL_PASSWORD, SRL_SOURCE_VER, SRL_TARGET_VER
source srl_config_env.sh
```

## 1 — Check for an existing template first

```bash
ls /home/joji/Go/workspace-settings/tools/srl-configs/
cat /home/joji/Go/workspace-settings/tools/srl-configs/<stem>.meta.json
```

If a matching template exists for the target NE type, skip to step 3.

## 2 — Dry-run: fix and save template

```bash
python3 srl_load_config.py \
    --config /path/to/flat_config.cfg \
    --ne-ip <TARGET_NE_IP> \
    --ne-id <NE_ID> \
    --ne-type 7250-IXR-SRL \
    --source-ne-ip <SOURCE_NE_IP> \
    --source-ver 25.10 --target-ver 25.10 \
    --save-template /home/joji/Go/workspace-settings/tools/srl-configs \
    --dry-run
```

## 3 — Load onto the NE

```bash
python3 srl_load_config.py \
    --config /path/to/flat_config.cfg \
    --ne-ip <TARGET_NE_IP> \
    --ne-id <NE_ID> \
    --ne-type 7250-IXR-SRL
```

## 4 — Reuse saved template on another NE of the same type

```bash
python3 srl_load_config.py \
    --config /home/joji/Go/workspace-settings/tools/srl-configs/<stem>_v2510_to_2510_fixed.cfg \
    --ne-ip <OTHER_NE_IP> \
    --ne-id <OTHER_NE_ID> \
    --ne-type 7250-IXR-SRL \
    --source-ver 25.10 --target-ver 25.10
```

Script warns if `--ne-type` differs from the template's recorded NE type.

## Key options

| Option | Default | Description |
|--------|---------|-------------|
| `--ne-id <IP>` | — | Target NE ID (system0 loopback); always stripped from source to preserve target's own |
| `--ne-type <TYPE>` | — | NE hardware type (e.g. `7250-IXR-SRL`); stored in metadata, used for mismatch warning |
| `--source-ne-ip <IP>` | — | IP of the NE the config was exported from (recorded in metadata) |
| `--save-template DIR` | — | Copy fixed config + metadata to `tools/srl-configs/` for reuse |
| `--keep-mgmt0-ip` | off | Apply mgmt0 static IP from source (default: strip it) |
| `--output-dir DIR` | same as config | Where to save the fixed file |
| `--dry-run` | off | Fix and save only, do not push to device |
| `--no-save-startup` | off | Skip `save startup` after commit |

**After loading:** TLS cert/key are always stripped. The target NE needs its
NSP CA-signed cert restored manually — see the full procedure in the skill.

Skill: `../../skills/srl-config-load/SKILL.md` (template workflow, cert
restoration, schema migration fixes, troubleshooting).
