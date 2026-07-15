---
name: nsp-repo-public-migration
description: >-
  Prepare a private NSP Go library or service repo for public GitLab group listing and Jenkins CI.
  Adds .go-make submodule, Jenkinsfile (build-pipeline-go release/3.0+), .ci_deps.json, catalog-info,
  USAGE/VERSIONING docs, and verifies make build/test/run-orbw-validate. Prompts for target public
  GitLab group (e.g. comm) and applies it to catalog-info and README URLs. After commits, directs
  user through Public-Project-Requirement-Checker and DevOps Teams promotion. Use when converting a
  private Go repo to NSP public-project requirements, or when asked to make a repo "ready for
  public listing" like comm-shared-go.
---

# NSP Go repo — public listing migration

Prepare a **private** Go repo so it passes NSP DevOps **public-project requirements** and builds
cleanly with the standard `.go-make` pipeline. **GitLab promotion to a public group** (for example
`comm/`) is a **separate DevOps ticket** — do not move the remote project in this skill.

**Canonical DevOps docs:**
- [Go build setup](http://orbw-web.ca.alcatel-lucent.com:8001/projects-and-builds/languages/go/)
- [New project guide](http://orbw-web.ca.alcatel-lucent.com:8001/projects-and-builds/projects/new-project-guide/)
- [Jenkinsfile / library versions](http://orbw-web.ca.alcatel-lucent.com:8001/projects-and-builds/pipelines/jenkinsfile/)

**Reference repos (already migrated in this workspace):**
- Pure Go module: `comm-client-kafka-go`
- Protobuf/gRPC module: `comm-notification-worker-protobuf-go`, `comm/comm-operator-worker-protobuf-go`
- Docker+Helm app: `comm/comm-layer-server` (uses `goDockerHelmPremadePipeline`)

---

## Agent policy

- Run `make build`, `make test`, and validations **without asking** until all pass.
- **Ask before** `git push`, posting to Teams, or running the checker Jenkins job on the user's behalf.
- **Do not** relocate the GitLab project to a public group — user files a DevOps ticket after checks pass.
- Pin **`build-pipeline-go@release/3.0`** (or newer per Jenkinsfile doc table). **Do not** copy
  `release/2.1` from older reference repos — verify the current doc/library table first.
- **Commit messages must not include** `Co-authored-by: Cursor <cursoragent@cursor.com>` (or any
  Cursor/agent co-author trailer). Use a plain subject/body only — see [Commit grouping](#commit-grouping).

---

## Pre-flight

**Ask the user for the target public GitLab group** (for example `comm`) if they have not
already provided it. Record it as `PUBLIC_GITLAB_GROUP` and use it for every **post-promotion**
repository URL in docs and `catalog-info.yaml` — see [Public GitLab group URLs](#public-gitlab-group-urls).

Also collect promotion-request fields (ask if missing — needed for the [DevOps Teams post](#devops-teams-promotion-post)):

| Variable | Source / example |
|----------|------------------|
| `REPO_NAME` | Directory or GitLab project name (e.g. `comm-notification-worker-protobuf-go`) |
| `PRIVATE_NAMESPACE` | Current private GitLab owner from `git remote` (e.g. `jojijose`) |
| `PRIVATE_PROJECT_URL` | `http://orbw-git.ca.alcatel-lucent.com/<PRIVATE_NAMESPACE>/<REPO_NAME>` |
| `PUBLIC_PROJECT_PATH` | `<PUBLIC_GITLAB_GROUP>/<REPO_NAME>` (e.g. `comm/comm-notification-worker-protobuf-go`) |
| `MAINTAINER_CSLS` | Comma-separated Nokia CSLs (e.g. `jojijose, tfasanga`) |
| `OWNER_CSL` | Requester's CSL for the checker job (e.g. `jojijose`) |
| `PROJECT_REASONING` | One short paragraph: what the repo does and why it should be public |
| `ADDITIONAL_BRANCHES` | Default: `master only` |
| `SIGNOFF_NAME` | First name for Teams post closing (e.g. `Joji`) |

The repo may still live under a private user namespace until DevOps promotes it; **catalog/README
URLs** reflect the post-promotion location; the **Teams post** uses the **private** URL for the
current project location.

1. Confirm repo type:
   - **Go module library** → `goModulePremadePipeline()`
   - **Container + optional Helm** → `goDockerHelmPremadePipeline(false|true)` (note spelling:
     `Pipeline` with **e** — older `release/2.1` repos used typo `goDockerHelmPremadePipline`)
2. Confirm `go.mod` uses `module nsp.nokia.com/<group>/<name>` (no `/vM` suffix until major ≥ 2).
3. Confirm `VERSION` file exists; Go modules use **`v` prefix** (for example `v0.1.3`).
4. If the module has upstream `nsp.nokia.com/...` dependencies, convert **base libraries first**
   (A → B → C) so Artifactory has modules before dependents build.

### `/vM` module path rule (v2+ only)

When major version ≥ 2, both `go.mod` **and** import paths must include `/vM`:

```go
module nsp.nokia.com/comm/my-lib/v2
import "nsp.nokia.com/comm/my-lib/v2/pkg/foo"
```

v0 and v1 modules omit the `/vM` suffix in the module path.

### Public GitLab group URLs

Use the **target public group** (`PUBLIC_GITLAB_GROUP`, e.g. `comm`), not the current private
owner namespace (e.g. `jojijose`). Derive the repo name from the directory or `git remote`
(`comm-client-kafka-go`).

| Pattern | Example (`group=comm`, repo `comm-client-kafka-go`) |
|---------|-----------------------------------------------------|
| HTTP browse | `http://orbw-git.ca.alcatel-lucent.com/comm/comm-client-kafka-go` |
| `go.mod` replace | `orbw-git.ca.alcatel-lucent.com/comm/comm-client-kafka-go` |
| `git clone` | `git clone http://orbw-git.ca.alcatel-lucent.com/comm/comm-client-kafka-go.git` |

**Files to update** (grep for old namespace before committing):

| File | Fields |
|------|--------|
| `catalog-info.yaml` | `metadata.annotations.backstage.io/source-location`, `metadata.links[].url` |
| `README.md` | Repository header link, `git clone`, `go.mod` `replace` examples |
| `USAGE.md` | GitLab `replace` / clone examples if present |

Do **not** change `.gitmodules` / `.go-make` URLs (those point at `build/pipeline/...`, not the
project repo). Already-public repos in the workspace may use `http://nsp.nokia.com/<group>/...`
instead of `orbw-git` — match the convention of sibling repos in the same group when unsure.

---

## Migration checklist

### 1. Add `.go-make` submodule

```bash
git config submodule.recurse true
git submodule add -b release/1.0 \
  git@orbw-git.ca.alcatel-lucent.com:build/pipeline/go/go-make.git .go-make
git submodule update --init --recursive --remote
git add .gitmodules .go-make
```

### 2. Add CI boilerplate

| File | Content |
|------|---------|
| [`.ci_deps.json`](http://orbw-web.ca.alcatel-lucent.com:8001/projects-and-builds/projects/ci-deps-json/) | Empty upstream arrays if no Jenkins build-chain deps |
| `Jenkinsfile` | See below |
| `build.sh` | `#!/bin/sh` + `make build` (executable) |
| `.gitignore` | Add `/build/` for test artifacts |

**`.ci_deps.json`** (no upstream NSP Jenkins deps):

```json
{
    "dependencies": {
        "upstream": {
            "autogenerated": [],
            "custom": []
        }
    }
}
```

**`Jenkinsfile`** — Go module:

```groovy
@Library("build-pipeline-go@release/3.0") l1
goModulePremadePipeline()
```

**`Jenkinsfile`** — container app (no Helm chart):

```groovy
@Library("build-pipeline-go@release/3.0") l1
goDockerHelmPremadePipeline(false)
```

### 3. Rewrite `Makefile`

Minimum for a **Go module**:

```makefile
include .go-make/go.mk
GO_VERSION=1.26
GO_SRC_DIR=./...

VERSION := $(shell cat VERSION)

.PHONY: build
build: go-build

.PHONY: test
test: go-test
```

- Set `GO_VERSION` to `M.m` matching `go.mod` (for example `1.26` for `go 1.26.2`).
- Set `GO_SRC_DIR=./...` when `.go` files are not in repo root (fixes `no Go files in /usr/src`).
- Keep custom dev targets (`tidy`, `version`, `push-tag`) with `#` help comments; **remove** a custom
  `help` target (`.go-make` provides `make help`).
- **Protobuf repos:** keep `make proto` but **do not** make `build` depend on `proto` — CI image has
  no `protoc`; commit generated `*.pb.go` and regenerate locally after `.proto` edits.

### 4. Documentation and Backstage

Use `PUBLIC_GITLAB_GROUP` in all GitLab URLs (see [Public GitLab group URLs](#public-gitlab-group-urls)).

| File | Purpose |
|------|---------|
| `catalog-info.yaml` | Backstage component entry (`type: library` or `service`) |
| `USAGE.md` | `go get`, local `replace`, GOPRIVATE note |
| `VERSIONING.md` | Tag push workflow from `VERSION` |
| `README.md` | Description, usage/API, build section, contact |

README build section must document:

```bash
git config submodule.recurse true
git submodule update --init --recursive
make build    # use BUILDER=docker on Linux if podman unavailable
make test
make run-orbw-validate   # requires ORBW_GITLAB_TOKEN (see Verification)
```

### 5. Align Go version

Bump `go` directive in `go.mod` to current NSP standard (for example `1.26.2`), then `go mod tidy`.

---

## Verification (must all pass)

```bash
# Linux without podman:
make BUILDER=docker build
make BUILDER=docker test

# Plain go (sanity, optional):
go build ./...
go test ./...
```

### `run-orbw-validate`

The `.go-make` target runs the NSP validation container. The container expects
**`ORBW_GITLAB_TOKEN`** (the Make rule passes `GITLAB_PRIVATE_TOKEN` but not `ORBW_GITLAB_TOKEN`).

```bash
export ORBW_GITLAB_TOKEN=<gitlab-pat>   # or source mr-review/gitlab_env.sh and map GITLAB_TOKEN
docker run --rm --pull=always \
  -e BRANCH_NAME -e ORBW_GITLAB_TOKEN -e GITLAB_PRIVATE_TOKEN="$ORBW_GITLAB_TOKEN" \
  -v "$(pwd):/app" \
  orbw-artifactory.ca.alcatel-lucent.com:8081/nokia-nsp-docker-virtual/validation-orbw-project-validations:1.1
```

Or with token exported:

```bash
ORBW_GITLAB_TOKEN="$GITLAB_TOKEN" make BUILDER=docker run-orbw-validate
```

Fix any validation failures before committing.

---

## Commit grouping

Use **HEREDOC** commits with **only** the intended message — no trailers:

```bash
git commit -m "$(cat <<'EOF'
Migrate to NSP Jenkins pipeline: add go-make, Jenkinsfile, .ci_deps.json

EOF
)"
```

**Do not** append `Co-authored-by: Cursor <cursoragent@cursor.com>` or similar agent attribution.
If a commit already has that trailer, amend with a clean message (only when amend rules allow) or
create a new commit after fixing the message.

Suggested messages:

1. `Migrate to NSP Jenkins pipeline: add go-make, Jenkinsfile, .ci_deps.json`
2. `docs: add catalog-info.yaml, USAGE.md, VERSIONING.md; expand README build section`
3. `ci: bump build-pipeline-go Jenkins library to release/3.0` (if bumping an already-migrated repo)

3. `ci: bump build-pipeline-go Jenkins library to release/3.0` (if bumping an already-migrated repo)

---

## After migration commits — user handoff

When all migration-related changes are **committed** (and **pushed** to `master` on the private
repo), **stop and hand off to the user**. Do not post to Teams or run the checker Jenkins job on
the user's behalf.

### Step 1: Run Public-Project-Requirement-Checker

Ask the user to run the checker and paste the **successful build URL** when it passes.

**Jenkins job:**
[Public-Project-Requirement-Checker](http://orbw-jenkins.ca.alcatel-lucent.com:32000/job/NSP/job/Developer-Tools/job/Public-Project-Requirement-Checker/)

**Docs:**
[Project Requirement Checker](http://orbw-web.ca.alcatel-lucent.com:8001/developer-tools/project-req-checker/)

| Parameter | Value |
|-----------|-------|
| `PROJECT_NAME` | `REPO_NAME` (GitLab project name, no group prefix) |
| `CSL` | `OWNER_CSL` |
| `BASE_BRANCH` | `master` |
| `GROUP_NAME` | `PUBLIC_GITLAB_GROUP` (e.g. `comm`) |
| `SKIP_CVE_SCAN` | Unchecked for the run used in the promotion request |

**Pass criteria:** no failed tests, **no skipped tests** (full CVE scan required for promotion).

If the checker fails, fix the reported gaps in the repo, commit, push, and re-run until green.

### Step 2: Request DevOps promotion (Teams)

After a **successful** checker run, ask the user to post in the nspOS DevOps Teams channel:

[Scrum - nspOS-devops Team](https://teams.microsoft.com/l/channel/19%3A2cf9f3b6c0c54352829e045c5a99040a%40thread.tacv2/Scrum%20-%20nspOS-devops%20Team?groupId=362529dd-fdc2-423e-9fe0-95eb87a08515&tenantId=5d471751-9675-428d-917b-70f44f9630b0)

Generate the post from the template below (fill placeholders; first line is the channel subject).

### DevOps Teams promotion post

```
Promote "<REPO_NAME>" to public repo

I would like to have my following private project added to the build pipeline.
Private project URL: <PRIVATE_PROJECT_URL>
Requested GitLab group: <PUBLIC_GITLAB_GROUP>
Requested project name: <PUBLIC_PROJECT_PATH>
Additional required branches besides master: <ADDITIONAL_BRANCHES>
List of maintainer CSLs: <MAINTAINER_CSLS>
Link to your successful Public Project Requirement Checker run: <CHECKER_BUILD_URL>
Project reasoning: <PROJECT_REASONING>
I have read and reviewed the public project requirements in the new project guide.

Thanks,
<SIGNOFF_NAME>
```

**Example** (`comm-notification-worker-protobuf-go`):

```
Promote "comm-notification-worker-protobuf-go" to public repo

I would like to have my following private project added to the build pipeline.
Private project URL: http://orbw-git.ca.alcatel-lucent.com/jojijose/comm-notification-worker-protobuf-go
Requested GitLab group: comm
Requested project name: comm/comm-notification-worker-protobuf-go
Additional required branches besides master: master only
List of maintainer CSLs: jojijose, tfasanga
Link to your successful Public Project Requirement Checker run: http://orbw-jenkins.ca.alcatel-lucent.com:32000/job/NSP/job/Developer-Tools/job/Public-Project-Requirement-Checker/<build-number>/
Project reasoning: A support Go library containing common Protobuf definitions to communicate between subscription service and mediation workers in the Communication Domain of NSP Services.
I have read and reviewed the public project requirements in the new project guide.

Thanks,
Joji
```

DevOps may request further changes or post an update when the repo is published.

### Step 3: After publication — dependent repo updates

When DevOps confirms the repo is live under `PUBLIC_PROJECT_PATH`, remind the user that
**consuming repos** may still reference the private namespace or old `go.mod` replace paths.

| What to update | Where |
|----------------|-------|
| `go.mod` `require` / `replace` | Any repo that depended on the private checkout |
| GitLab clone URLs in README/docs | Downstream repos and runbooks |
| `catalog-info.yaml` `consumedBy` / deps | If Backstage relationships were provisional |

**Agent follow-up (when user confirms publication):**

1. `grep` workspace for old paths: `jojijose/<REPO_NAME>`, private module replaces, stale clone URLs.
2. List affected repos (from `catalog-info.yaml` `consumedBy`, `go.mod`, or README cross-refs).
3. Offer to migrate each dependent repo to `nsp.nokia.com/...` + public GitLab replace path.

Track migration status per repo:

| Phase | Status |
|-------|--------|
| Local migration commits | done / in progress |
| Pushed to private `master` | done / pending |
| Checker green | done / pending — need build URL |
| Teams promotion posted | done / pending |
| DevOps published to public group | done / pending |
| Dependents updated | done / pending / N/A |

---

## DevOps promotion reference

The
[Project Requirement Checker](http://orbw-web.ca.alcatel-lucent.com:8001/developer-tools/project-req-checker/)
Jenkins job is the **authoritative gate** before Teams promotion:

- No failed tests, **no skipped tests**
- Checks versioning, pipeline currency, README, `.gitignore`, `.ci_deps.json`, Make submodule, etc.
- CVE scan on dependencies (and Docker image if applicable)
- `SKIP_CVE_SCAN` may be used for quick iteration only — promotion requires a full pass

Promotion is requested via the [Teams channel](#step-2-request-devops-promotion-teams), not by the agent.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `Error 127` on `make build` | `make BUILDER=docker build` (podman not installed) |
| `no Go files in /usr/src` | Set `GO_SRC_DIR=./...` in Makefile |
| `Gitlab token is unset` on validate | Export `ORBW_GITLAB_TOKEN` (see Verification) |
| `make: overriding recipe for target 'help'` | Remove custom `help` target from Makefile |
| `missing go.sum entry` | `go mod tidy` inside build image or locally |
| Mixed-PAT legacy private deps | See [Private Go modules (legacy)](http://orbw-web.ca.alcatel-lucent.com:8001/projects-and-builds/legacy/private-go-modules/) |

---

## Related skills

- **build-go-repo** — delta coverage and Jenkins `[jenkins]` baseline after migration
- **mr-review** — MR review before merge to master (pre-promotion branch should be `master`)
