---
name: mdm-patch-load
description: >-
  End-to-end MDM patch workflow: local Windows code changes → local Gradle build + branch + commit (via build-java-repo) → branch validation → higher-level SNAPSHOT version threading (mdm-core-install, nsp-mdm-server; mdm-bom is never touched) → remote builds on build server (100.127.42.213) in dependency order → docker image build for nsp-mdm-server → SCP image + helm chart to cluster node → helm delete/reinstall on the K8s cluster. Use when the user asks to patch, build, deploy, load, or push MDM changes to a cluster; mentions mdm-patch-load, nsp-mdm-server docker build, helm reinstall mdm-server, or nerdctl load.
---

# MDM Patch & Load Skill

## Configuration — read this first

All variable values live in `config.env` (copy from `config.env.example` and edit):

| Variable | Default / Example | Purpose |
|---|---|---|
| `MDM_BUILD_SERVER` | `jojijose@100.127.42.213` | SSH target for remote Gradle builds |
| `MDM_REMOTE_REPO_ROOT` | `/NSP/MED` | Repos root on build server |
| `MDM_CLUSTER_NODE` | `root@100.127.194.35` | Jump-host / node1 for image load (current: 100.127.194.35) |
| `MDM_CLUSTER_DIR` | `/opt/nsp/mdm` | Dir on node1 for tar + helm chart |
| `MDM_SERVER_VERSION` | `25.0.0-rel.12-SNAPSHOT` | nsp-mdm-server image/chart version tag |
| `MDM_REGISTRY` | `orbw-artifactory.ca.alcatel-lucent.com:8081/nokia-nsp-docker-virtual` | Docker registry prefix |
| `MDM_SNAPSHOT_VERSION` | `1.5.0-rel.13-SNAPSHOT` | SNAPSHOT version for shared-* libs |
| `MDM_HELM_VALUES` | `/opt/nsp/config/helm/values/mdm/mdm-server/values.yaml` | Helm values file on node1 |

---

## Dependency order (always follow this sequence)

```
shared-ssh-client          <- lower-level (handled by build-java-repo)
  -> shared-netconf-client <- lower-level (handled by build-java-repo)
      -> mdm-core-netconf  <- lower-level (handled by build-java-repo)
          -> mdm-bom               <- SNAPSHOT overrides go HERE in dependencies_mdm.gradle
              -> mdm-core-install  <- higher-level (this skill -- branch only, no file changes)
                  -> nsp-mdm-server <- higher-level (this skill -- branch only)
```

Only process repos touched by the current patch. Determine which repos are changed before starting.

---

## Phase 1 -- Local code changes, build, branch & commit

**Delegate entirely to the `build-java-repo` skill** for each lower-level changed repo (shared-ssh-client, shared-netconf-client, mdm-core-netconf) in dependency order.

`build-java-repo` covers:
- Local Gradle build (`gradle7 clean build`)
- Working branch creation: `jojijose/<functionality-name>` from master
- Staging only patch-specific files (explicit `git add`, no `git add -A`)
- Commit with a summary message
- Delta coverage validation

Do not proceed to Phase 2 until all changed lower-level repos have `BUILD SUCCESSFUL` and are committed on their branch.

---

## Phase 2 -- Branch validation (after build-java-repo)

Before triggering any remote builds, confirm the branch state of every changed repo.

For each changed repo (Windows Git Bash):

```bash
cd /c/NSP/MDM/<repo>
git branch --show-current        # must show jojijose/<name>, not master
git log --oneline -3             # confirm patch commit is at HEAD
git status                       # must be clean (no untracked/modified files left over)
```

**Record the branch name** -- it will be used verbatim in Phase 4 on the remote build server.

If a repo is still on `master` or has uncommitted changes, go back to Phase 1 and complete `build-java-repo` for that repo first.

---

## Phase 3 -- SNAPSHOT version threading

### 3a. Lower-level repos -- validate only (build-java-repo already did this)

Confirm the following edits are already committed on the branch for each affected lower-level repo:

| Repo | What to verify |
|---|---|
| `shared-ssh-client` | `version = '<MDM_SNAPSHOT_VERSION>'` in `build.gradle` |
| `shared-netconf-client` | `version = '<MDM_SNAPSHOT_VERSION>'` in `build.gradle`; consumer dep on `shared-ssh-client:<MDM_SNAPSHOT_VERSION>` |
| `mdm-core-netconf` | consumer dep on `shared-netconf-client:<MDM_SNAPSHOT_VERSION>` in `build.gradle` |

Run `git show HEAD -- build.gradle` in each repo to confirm without needing to open the file.

If any of these are missing, return to Phase 1 / `build-java-repo` to add and commit them.

### 3b. Higher-level repos -- this skill makes these edits

#### mdm-bom -- add SNAPSHOT overrides in `dependencies_mdm.gradle`

**SNAPSHOT overrides go in `mdm-bom/dependencies_mdm.gradle`.** This is the single source of truth for dependency versions across all higher-level repos. Update the existing version entries for each patched lib directly (do not add duplicate blocks):

```groovy
// In mdm-bom/dependencies_mdm.gradle -- update these existing lines:
dependency "com.nokia.nsp.shared:shared-ssh-client:1.5.0-rel.13-SNAPSHOT"
dependency "com.nokia.nms.osgi:shared-netconf-client:17.21.0-rel.6-SNAPSHOT"
dependency "com.nokia.nsp.mdm:mdm-core-netconf:1.18.0-rel.22-SNAPSHOT"
dependency "com.nokia.nsp.mdm:mdm-core-cli:1.12.0-rel.154-SNAPSHOT"
```

To edit on the remote build server (use Python to avoid shell quoting issues):

```python
# /tmp/patch_mdm_bom.py
path = '/NSP/MED/mdm-bom/dependencies_mdm.gradle'
with open(path) as f:
    content = f.read()
replacements = [
    ('shared-ssh-client:1.4.0-rel.1', 'shared-ssh-client:1.5.0-rel.13-SNAPSHOT'),
    ('shared-netconf-client:17.21.0-rel.6', 'shared-netconf-client:17.21.0-rel.6-SNAPSHOT'),
    ('mdm-core-netconf:1.18.0-rel.+', 'mdm-core-netconf:1.18.0-rel.22-SNAPSHOT'),
    ('mdm-core-cli:1.12.0-rel.+', 'mdm-core-cli:1.12.0-rel.154-SNAPSHOT'),
]
for old, new in replacements:
    content = content.replace(old, new)
with open(path, 'w') as f:
    f.write(content)
```

Branch + commit (`dependencies_mdm.gradle` only) on the **remote server**:

```bash
cd /NSP/MED/mdm-bom
git checkout master && git pull --rebase origin master
git checkout -b jojijose/<context-based-name> master
git add dependencies_mdm.gradle
git commit -m "Pin SNAPSHOT deps for <patch-name>: <lib list>"
```

Then build and publish `mdm-bom` to local Maven before building downstream repos:

```bash
/opt/gradle-7.6.6/bin/gradle clean build publishToMavenLocal
```

> `mdm-core-install/dependencies_mdm.gradle` should have **no** SNAPSHOT overrides — leave it clean. The BOM provides the pinned versions.

#### mdm-core-install -- branch only, no file changes

`mdm-core-install` picks up the SNAPSHOT versions from the `mdm-bom` local Maven artifact. No `dependencies_mdm.gradle` edits needed.

```bash
cd /c/NSP/MDM/mdm-core-install
git checkout master && git pull --rebase origin master
git checkout -b jojijose/<context-based-name> master
# nothing to commit
```

#### nsp-mdm-server -- branch only, no file changes

`nsp-mdm-server` reads `mdm-core-install`'s version dynamically from `../mdm-core-install/gradle.properties`. No `build.gradle` edits needed.

```bash
cd /c/NSP/MDM/nsp-mdm-server
git checkout master && git pull --rebase origin master
git checkout -b jojijose/<context-based-name> master
# nothing to commit
```

---

## Phase 4 -- Remote builds on build server (100.127.42.213)

### Identify the branch to use

The branch was created by `build-java-repo` (Phase 1) or this skill (Phase 3b). For each repo, check locally:

```bash
cd /c/NSP/MDM/<repo>
git branch --show-current
```

Use the exact branch name returned -- do not guess or construct a new one.

### Build on the remote server

SSH into the build server:

```bash
ssh jojijose@100.127.42.213
```

**Dependency order for remote builds:**

```
shared-ssh-client
  → shared-netconf-client
      → mdm-core-netconf
          → mdm-core-cli        (use JAVA_TOOL_OPTIONS for encoding; publish via artifactory publication)
              → mdm-bom         (SNAPSHOT overrides live here; publish to local Maven first)
                  → mdm-core-install
                      → nsp-mdm-server  (Phase 5 -- Docker + Helm)
```

For **each repo in dependency order**, run:

```bash
cd /NSP/MED/<repo>

# Sync master, then switch to the patch branch
git checkout master
git pull --rebase origin master
git fetch origin <branch-name>
git checkout <branch-name>
git pull origin <branch-name>

# Build and publish to local Maven cache
# Use full path -- the build server has Gradle 7.6.6 at /opt/gradle-7.6.6/bin/gradle
/opt/gradle-7.6.6/bin/gradle clean build publishToMavenLocal
```

**Special cases:**

- **mdm-core-cli**: has UTF-8 copyright chars in source; set encoding env var, and its `localJarPublication` metadata task fails — use the `artifactoryPublications` publication instead:
  ```bash
  cd /NSP/MED/mdm-core-cli
  JAVA_TOOL_OPTIONS='-Dfile.encoding=UTF-8' /opt/gradle-7.6.6/bin/gradle clean build publishArtifactoryPublicationsPublicationToMavenLocal
  ```

- **mdm-bom**: must be built and published to local Maven **before** `mdm-core-install` picks up the SNAPSHOT versions:
  ```bash
  cd /NSP/MED/mdm-bom
  /opt/gradle-7.6.6/bin/gradle clean build publishToMavenLocal
  ```

Replace `<branch-name>` with the exact branch recorded in Phase 2 / Phase 3b for that repo.

Wait for `BUILD SUCCESSFUL` before moving to the next repo in the chain.

If a build fails: investigate on the build server (`gradle clean build --info`), fix the cause on Windows, push the fix to the same branch, then pull and retry on the build server.

---

## Phase 5 -- nsp-mdm-server: Docker image build & copy to cluster node

Run on the build server after all upstream repos are published:

```bash
cd /NSP/MED/nsp-mdm-server

# Step 1: Gradle build -- MUST run before docker-build or helm packaging.
# This cleans stale build output and repopulates build/tar with fresh artifacts.
/opt/gradle-7.6.6/bin/gradle clean build

# Step 2: Build Docker image via make
# NOTE: `makesub` alias (git submodule init for .java-make) must be run once
# before `make docker-build` works -- one-time setup, already done.
make docker-build

# Confirm the exact image tag from build output before continuing
docker images | grep nsp-mdm-server

# Save docker image
docker save orbw-artifactory.ca.alcatel-lucent.com:8081/nokia-nsp-docker-virtual/nsp-mdm-server:<MDM_SERVER_VERSION> \
  > nsp-mdm-server.tar

# Step 3: Package helm chart using make helm-build
# This produces build/nsp-mdm-server-<version>.tgz (e.g. build/nsp-mdm-server-26.0.0-rel.105.tgz)
# NOTE: `makesub` must have been run once first (initialises .java-make submodule).
cd /NSP/MED/nsp-mdm-server
make helm-build

# Confirm chart filename from the make output (version matches docker image tag, no -SNAPSHOT suffix)
ls build/nsp-mdm-server-*.tgz
```

Copy to cluster node -- clean the target dir first:

```bash
ssh root@<MDM_CLUSTER_NODE> "mkdir -p /opt/nsp/mdm && rm -f /opt/nsp/mdm/nsp-mdm-server.tar /opt/nsp/mdm/nsp-mdm-server-*.tgz"

scp /NSP/MED/nsp-mdm-server/nsp-mdm-server.tar root@<MDM_CLUSTER_NODE>:/opt/nsp/mdm/
scp /NSP/MED/nsp-mdm-server/build/nsp-mdm-server-<MDM_SERVER_VERSION>.tgz root@<MDM_CLUSTER_NODE>:/opt/nsp/mdm/
```

> If SSH key auth fails with "Permission denied", stop and ask the user to verify key setup before proceeding.

---

## Phase 6 -- Load image and reinstall Helm chart on cluster node

SSH into the cluster node:

```bash
ssh root@<MDM_CLUSTER_NODE>
cd /opt/nsp/mdm
```

Run the following sequence:

```bash
# 1. Remove existing Helm release
helm delete -n nsp-psa-privileged mdm-server

# 2. Extract helm chart (make helm-build produces nsp-mdm-server-<version>.tgz
#    which unpacks to an nsp-mdm-server/ directory)
rm -rf /opt/nsp/mdm/nsp-mdm-server
cd /opt/nsp/mdm
tar zxvf nsp-mdm-server-<MDM_SERVER_VERSION>.tgz

# 3. Load docker image into containerd
nerdctl load < nsp-mdm-server.tar

# 4. Install / upgrade with values
# Using upgrade --install so the command is idempotent (works for both first install and re-deploy)
helm upgrade mdm-server --install /opt/nsp/mdm/nsp-mdm-server \
  --namespace nsp-psa-privileged \
  --timeout 900s \
  --enable-dns \
  -f /opt/nsp/config/helm/values/mdm/mdm-server/values.yaml \
  --set image.tag=<MDM_SERVER_VERSION>
```

Replace `<MDM_SERVER_VERSION>` with the exact docker image tag confirmed in Phase 5 (e.g. `26.0.0-rel.105` -- note: no `-SNAPSHOT` suffix in the docker tag).

Verify the pod comes up:

```bash
kubectl get certificates -n nsp-psa-privileged      # both external+internal must be READY
kubectl get pods -n nsp-psa-privileged | grep mdm-server  # must show 2/2 Running
```

---

## Checklist (copy and track progress)

```
Phase 1 -- Local build, branch & commit (via build-java-repo)
- [ ] shared-ssh-client      BUILD SUCCESSFUL, on jojijose/... branch, committed
- [ ] shared-netconf-client  BUILD SUCCESSFUL, on jojijose/... branch, committed
- [ ] mdm-core-netconf       BUILD SUCCESSFUL, on jojijose/... branch, committed

Phase 2 -- Branch validation
- [ ] All changed repos: git branch --show-current shows jojijose/<name>
- [ ] git status clean on each repo
- [ ] Branch names recorded for use in Phase 4

Phase 3a -- Lower-level SNAPSHOT versions (validate only)
- [ ] shared-ssh-client: version = SNAPSHOT in build.gradle
- [ ] shared-netconf-client: references shared-ssh-client SNAPSHOT
- [ ] mdm-core-netconf: references shared-netconf-client SNAPSHOT

Phase 3b -- Higher-level SNAPSHOT threading (this skill)
- [ ] mdm-core-install: SNAPSHOT overrides added in dependencies_mdm.gradle + committed
- [ ] nsp-mdm-server: branched from master (no file changes needed)

Phase 4 -- Remote builds (build server 100.127.42.213)
- [ ] shared-ssh-client      BUILD SUCCESSFUL + publishToMavenLocal
- [ ] shared-netconf-client  BUILD SUCCESSFUL + publishToMavenLocal
- [ ] mdm-core-netconf       BUILD SUCCESSFUL + publishToMavenLocal
- [ ] mdm-core-install       BUILD SUCCESSFUL + publishToMavenLocal

Phase 5 -- nsp-mdm-server Docker build & SCP
- [ ] gradle clean build succeeded (MUST run first -- refreshes build/tar)
- [ ] make docker-build succeeded
- [ ] make helm-build succeeded -> build/nsp-mdm-server-<version>.tgz confirmed
- [ ] docker image tag confirmed (docker images | grep nsp-mdm-server)
- [ ] nsp-mdm-server.tar SCP'd to cluster node
- [ ] nsp-mdm-server-<version>.tgz SCP'd to cluster node

Phase 6 -- Cluster load & helm install
- [ ] helm delete mdm-server
- [ ] nsp-mdm-server/ dir cleaned; chart extracted from tgz
- [ ] nerdctl load image
- [ ] helm install succeeded (chart at /opt/nsp/mdm/nsp-mdm-server)
- [ ] Certificates nsp-mdm-server-external-tls + internal-tls: READY
- [ ] Pod 2/2 Running
```

---

## Common issues

| Symptom | Fix |
|---|---|
| Remote build can't resolve SNAPSHOT dependency | Previous repo in chain didn't `publishToMavenLocal` -- rebuild it first |
| `docker save` tag not found | Image built with different tag -- check `docker images \| grep nsp-mdm-server` |
| SCP "Permission denied (publickey)" | SSH key not installed on target; stop and ask user to fix key auth |
| `helm upgrade --install` fails: cannot re-use name | Run `helm delete -n nsp-psa-privileged mdm-server` first, then retry |
| Pod stuck at `Init:0/1` with `secret "nsp-tls" not found` | Old chart was used -- run `make helm-build` and redeploy with the generated tgz |
| `helm install` fails: Certificate exists and cannot be imported | Manually-created Certificate conflicts with helm -- `kubectl delete certificate <name> -n nsp-psa-privileged` then reinstall |
| Pod CrashLoopBackOff after install | Check `kubectl logs -n nsp-psa-privileged <pod>` for startup errors |
| nerdctl load slow / hangs | Image is large (~1 GB+); wait at least 5 min before assuming hung |
| Branch not found on remote build server | Branch wasn't pushed -- push from Windows first: `git push origin <branch-name>` |

## Additional reference

- Local build, branch workflow, delta coverage: [build-java-repo skill](../build-java-repo/SKILL.md)
- Cluster server IP is environment-specific -- always confirm `MDM_CLUSTER_NODE` from `config.env` or user input before Phase 5
