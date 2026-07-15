---
name: gradle-mdm-java-upgrade
description: Runs, adapts, and authors Gradle or Java version upgrade migrations for MDM repos. Knows the full step-a-through-g workflow (clone, submodule, reference files, build.gradle transforms, branch, commit, push MR, verify build), the env-var configuration pattern (GRADLE7_USER, GIT_HOST, GRADLE7_BASE, etc.), and how to extend the command and scripts for a new target version. Use when the user asks to run a Gradle migration, upgrade to a new Gradle version, upgrade Java source/target compatibility, adapt the gradle7-migrate command for a future version, or troubleshoot a migration run.
---

# Gradle / Java Upgrade Skill (MDM repos)

## Prerequisites

This skill depends on the **mdm-bom** repository for its command definitions, migration
scripts, and environment templates. Before running or adapting anything, verify `mdm-bom`
is present in the workspace:

```bash
ls -d "$HOME/Go/mdm-bom" 2>/dev/null
```

**If `mdm-bom` is not found:** stop and ask the user to add the `mdm-bom` repo to the
Cursor workspace (File → Add Folder to Workspace → select the local `mdm-bom` clone).
Do not attempt to run migration scripts or read command files until `mdm-bom` is available.

## Source files (always read before acting)

| File | Purpose |
|---|---|
| `mdm-bom/.cursor/commands/gradle7-migrate.md` | Canonical command — full workflow steps a–g |
| `mdm-bom/.cursor/scripts/gradle7-migrate-full.sh` | Full automation (clone + reference + build.gradle + branch + push) |
| `mdm-bom/.cursor/scripts/update-build-gradle-and-push.sh` | Apply build.gradle changes only (already-cloned repos) |
| `mdm-bom/.cursor/scripts/gradle7-env.sh` | Env var config template (copy and edit per user) |
| `MDMProj/.cursor/scripts/gradle7-env.sh` | Workspace-local copy of env template |

Read the command and both scripts before running or adapting anything.

## Configuration (env vars)

Source `mdm-bom/.cursor/scripts/gradle7-env.sh` or set manually in Git Bash:

```bash
export GRADLE7_USER=yourname          # GitLab username (required)
export GIT_HOST=orbw-git.ca.alcatel-lucent.com
export GRADLE7_BASE=/c/NSP/MDM/Gradle7
export GRADLE7_REF_REPO=/c/NSP/MDM/shared-common-osgi
export GRADLE7_BRANCH=${GRADLE7_USER}/grade7_migration
export MR_REVIEWERS="@reviewer1 @reviewer2"
export MR_TITLE="Updates for Gradle 7.6.3 and Make"
```

## Running the current migration

```bash
# Full run (clone + migrate all repos):
source mdm-bom/.cursor/scripts/gradle7-env.sh
bash mdm-bom/.cursor/scripts/gradle7-migrate-full.sh

# Single repo:
REPO=mdm-core-common bash mdm-bom/.cursor/scripts/gradle7-migrate-full.sh

# Build.gradle fixes only (repos already cloned and branched):
bash mdm-bom/.cursor/scripts/update-build-gradle-and-push.sh

# Dry run (diff, no commit/push):
DRY_RUN=1 bash mdm-bom/.cursor/scripts/update-build-gradle-and-push.sh
```

Step-by-step (agent-driven): invoke `/gradle7-migrate` in Cursor chat, or reference the command file directly.

## Adapting for a future Gradle or Java upgrade

When a new migration is needed (e.g. Gradle 8, Java 17→21), follow this pattern:

### 1. Identify the delta

Run `git diff <old-commit> <new-commit> build.gradle` on a reference repo that has already been upgraded. Every `sed` transform in the scripts maps to one line of that diff.

### 2. Create new versioned copies

```
mdm-bom/.cursor/commands/gradle8-migrate.md       ← copy of gradle7-migrate.md
mdm-bom/.cursor/scripts/gradle8-migrate-full.sh   ← copy of gradle7-migrate-full.sh
mdm-bom/.cursor/scripts/gradle8-env.sh            ← copy of gradle7-env.sh
```

Update the env var names (`GRADLE8_*`), branch name, MR title, and script references throughout.

### 3. Update `apply_build_gradle_changes()` in the new script

Each migration step follows this pattern inside the function:

```bash
# <step description>
sed -i 's/<old-pattern>/<new-pattern>/g' "$f"
```

See `upgrade-patterns.md` for the full catalogue of build.gradle transforms from Gradle 6→7. Apply the same structure for new transforms.

### 4. Update the repo list

The `MDM_CORE_REPOS` and `OTHER_REPOS` arrays in the full script come from `dependencies_mdm.gradle`. Re-derive them from the BOM for each migration cycle if repos have been added or removed.

### 5. Update the command file

- **Configuration table**: change variable names and defaults to the new version.
- **Step c) build.gradle**: list the new transforms matching the new `apply_build_gradle_changes()`.
- **Step d/f**: update branch name pattern and MR title.
- **Optional section**: update script references to the new versioned scripts.

### 6. Update MDMProj stub

`MDMProj/.cursor/commands/<new-name>-migrate.md` — 6-line stub pointing to the new mdm-bom command.

## Key workflow steps (summary)

Steps are lettered a–g in the command file. All work happens under `$GRADLE7_BASE`.

| Step | What happens |
|---|---|
| a | Clone repo (skip if exists) |
| b | Add `.java-make` submodule |
| c | Copy `.gitmodules`, `Makefile`, `Jenkinsfile` from ref repo; patch `build.gradle` |
| d | `git checkout -b $GRADLE7_BRANCH master` |
| e | `git add -A && git commit` |
| f | `git push` with GitLab MR options |
| g | `source ~/set-j17-version.sh && gradle7` — verify `BUILD SUCCESSFUL` |

**mdm-core-* repos:** process one at a time (clone → a–g → next). All others: sequential.

Step g cannot run from a Windows agent shell (E_ACCESSDENIED); tell the user to run it manually in Git Bash.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Could not find method bundle()` | Bnd plugin not applied — skip the manifest→bundle transform (step 9 guard) |
| `runtime` config still present after sed | Check for `runtimeOnly` false-positive matches; re-run `update-build-gradle-and-push.sh` with `DRY_RUN=1` to inspect |
| Push rejected | Branch already exists on remote — `git checkout $GRADLE7_BRANCH` instead of `-b` |
| Submodule add fails | `.java-make` already in `.gitmodules` — skip; run `git submodule update --init --recursive --remote` only |
| BUILD FAILURE after step g | Read error; common causes: missing `implementation` config, old `compile` config remaining, wrong Bnd version |

## Additional reference

- Full build.gradle transform catalogue: see [upgrade-patterns.md](upgrade-patterns.md)
