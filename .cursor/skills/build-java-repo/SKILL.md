---
name: build-java-repo
description: Builds MDM Java repos using Gradle in Git Bash with Java 17. Agents should run gradle7 (clean build / defaultTasks / targeted tasks) as often as validation requires without asking permission. After changes to production or test code (or test classpath), regenerate history.diff from the correct merge-base with origin/master, run gradle7 deltaCoverage, and add UTs until rules pass (bounded retries; stop and report if still failing). Documents bash.exe -lc invocation, shell reuse, Orbweb dep checks for test libs, and failure triage.
---

# Build Java Repo

**Discovery:** Cursor lists project skills only from workspace folders that contain `.cursor/skills/`. A copy of this skill is also installed at `C:\Users\jojijose\.cursor\skills\build-java-repo\SKILL.md` so it appears in the Skills picker for multi-root workspaces that omit `MDMProj`.

## Agent policy — run builds without asking

When this skill applies (compile/test validation, fixes after `build.gradle` or code edits, multi-step publish chains): **invoke `gradle7 clean build`, `gradle7`, or focused tasks (`:compileJava`, `:test`, `publishToMavenLocal`, …) as often as needed** via the Shell tool (e.g. `bash.exe -lc "source ~/set-j17-version.sh && cd /c/NSP/MDM/<repo> && …"`). **Do not ask the user for permission** to run shell/Gradle commands. **Only ask before `git commit` or `git push`** (unless the user already instructed to commit/push in the same request). If the user keeps a separate Git Bash open for visible logs, you may **also** paste the same commands for them to run there — that does not replace agent-driven builds when validation is needed.

After edits that affect delta coverage (see **Delta coverage** below), also run **`gradle7 deltaCoverage`** in the same way (regenerate `history.diff` first). Only stop and report if the tool or environment refuses the command (then describe the error).

## Agent / Cursor Shell — Git Bash (working invocation)

The Cursor Shell often starts in **PowerShell**. To run Gradle with the same environment as a local developer, invoke **Git for Windows `bash.exe`** with a **login** shell so `~` and `set-j17-version.sh` resolve correctly.

### Resolve `bash.exe` (try in order)

1. `%LOCALAPPDATA%\Programs\Git\bin\bash.exe` (common user install)
2. `%ProgramFiles%\Git\bin\bash.exe` (common system install)

### One-shot build (copy-paste safe)

PowerShell (replace `<repo>` and adjust `bash.exe` path if needed):

```powershell
& "$env:LOCALAPPDATA\Programs\Git\bin\bash.exe" -lc "source ~/set-j17-version.sh && cd /c/NSP/MDM/<repo> && gradle7 clean build"
```

If `bash.exe` lives under Program Files instead:

```powershell
& "$env:ProgramFiles\Git\bin\bash.exe" -lc "source ~/set-j17-version.sh && cd /c/NSP/MDM/<repo> && gradle7 clean build"
```

- Use **`-lc`** (login + command) so `~/set-j17-version.sh` is found and Java 17 is on `PATH`.
- Paths inside Bash use **`/c/NSP/MDM/...`** (Git Bash style).

### Build command: `gradle7 clean build` or `gradle7`

- Prefer **`gradle7 clean build`** when validating changes (clean output, consistent with a full CI-style run).
- **`gradle7`** alone is fine when the repo’s **`defaultTasks`** already do what you need (for example `defaultTasks 'clean', 'build'` — a bare `gradle7` runs those tasks in order).
- For one-off tasks, still use explicit goals (e.g. `gradle7 publishToMavenLocal`, `gradle7 :compileJava`).

### Reuse the same shell for all rebuilds (agent work)

1. **First command in a terminal session** should establish Java + repo: run the full `-lc "source ~/set-j17-version.sh && cd /c/NSP/MDM/<repo> && …"` chain (or set Shell **`working_directory`** to `C:\NSP\MDM\<repo>` and still prefix with `source ~/set-j17-version.sh` once per new shell).
2. **Follow-up Gradle commands** in the **same** terminal session: stay in that repo directory and run **`gradle7 clean build`**, **`gradle7`**, **`gradle7 test`**, etc. **Do not** spawn a fresh PowerShell→Bash chain for every trivial rebuild unless the session ended or `working_directory` reset.
3. When using the Shell tool with a persistent session, set **`working_directory`** to **`C:/NSP/MDM/<repo>`** (or the equivalent path) and reuse that same session for `:compileJava`, `:test`, **`gradle7 clean build`** / **`gradle7`**, and `publishToMavenLocal` after Java is sourced once in that session.

Interactive developers can still type `gitbash` in PowerShell and then use manual `source` + `cd` as below.

### User’s open Git Bash (visible activity logs)

The agent **cannot attach** to a specific Cursor terminal tab (for example the MINGW64 session where you already ran `git diff … > history.diff`). When you want **full Gradle output in your own window**:

1. Keep **one Git Bash** open with `cd /c/NSP/MDM/<repo>` (and branch as needed).
2. Run **`source ~/set-j17-version.sh` once per new Bash** before **`gradle7`**. If Gradle fails configuring `buildscript` / `classpath` with “consumer needed Java 8” vs “component compatible with Java 17”, the daemon was started without Java 17 — stop daemons (`gradle7 --stop`) and **`source ~/set-j17-version.sh`** again, then retry.
3. The agent may **print the exact command block** here for you to **copy-paste** into that terminal so you see the same `gradle7 clean build`, `gradle7 test …`, or **`gradle7 deltaCoverage`** logs locally.

For **delta coverage** in that shell, prefer a **merge-base** (not a stale hardcoded SHA) unless you intentionally match CI:

```bash
BASE=$(git merge-base HEAD origin/master 2>/dev/null || git merge-base HEAD master)
git diff "$BASE" > history.diff
gradle7 deltaCoverage
```

---

## Workflow (interactive Git Bash)

### Step 1 — Launch Git Bash from PowerShell

```powershell
gitbash
```

### Step 2 — Source Java 17

```bash
source ~/set-j17-version.sh
```

Verify: `java -version` should report Java 17.

### Step 3 — Navigate to the repo

```bash
cd /c/NSP/MDM/<repo>
```

### Step 4 — Run the build

```bash
gradle7 clean build
```

If the repo defines suitable **`defaultTasks`**, you can run:

```bash
gradle7
```

Watch for `BUILD SUCCESSFUL`.

---

## Delta coverage (`history.diff` + `gradle7 deltaCoverage`)

> **Plugin note — do NOT re-declare `jacoco`, `jacocoTestReport`, or `deltaCoverageReport` in `build.gradle` for repos that already apply `orbweaver-build` or `nsp-mdm-dependencies`.** Those plugins provide `deltaCoverage` and JaCoCo integration automatically. Adding a duplicate `apply plugin: 'jacoco'` / `deltaCoverageReport {}` block causes conflicts. Only add `test { jvmArgs(...) }` overrides if the test task needs Java 17 `--add-opens` for Mockito compatibility.

Repos that enforce Jacoco/Bnd **delta** rules (e.g. `branches covered ratio … expected minimum is 0.7`) need an up-to-date **`history.diff`** before **`gradle7 deltaCoverage`**. Do this **after each substantive change** to `src/main`, `src/test`, `bnd.bnd`, or test-related `build.gradle` lines.

### MANDATORY — Stage all new files before committing

When preparing a commit, always stage **every file the agent introduced**, not just modified ones. New source files, test files, and config additions are untracked by default and silently excluded from `git commit` unless explicitly added.

> **`history.diff` must NOT be staged or committed.** It is a local working file only — regenerate it on demand, never commit it to the branch.

Run `git status` after all edits and before committing. Stage new files explicitly:

```bash
# Stage new + modified files relevant to the change (never include history.diff)
git add path/to/NewFile.java src/test/java/com/example/NewTest.java build.gradle

# Or stage everything in a known directory (e.g. a new test package)
git add src/test/java/com/example/newpackage/

# Confirm staged set before committing
git status
```

Do **not** rely on `git commit -a` — it only picks up *modified* tracked files, not *untracked* new ones.

> **Rule:** After writing any new file (production class, test class, `SKILL.md` update), immediately follow with `git add <that-file>` so the subsequent commit includes it. `git status` is the authoritative check — if a file shows under *Untracked files*, it is NOT in the commit. Never add `history.diff`.

---

### MANDATORY — Working branch before any code change or `deltaCoverage` run

> **Do NOT skip this step.** Always ensure you are on a proper feature branch before editing files, generating `history.diff`, or running `gradle7 deltaCoverage`. Commits to `master` directly are not accepted.

#### Branch naming — MUST reflect the code functionality, not the tooling

Branch names use the pattern **`jojijose/<new-branch-name>`** where **`<new-branch-name>`** describes **what the code does**, not the tool or process used to validate it.

| Good (functionality) | Bad (tooling/process) |
|---|---|
| `jojijose/async-event-readstream` | `jojijose/netconf-delta-coverage` |
| `jojijose/async-event-netconf` | `jojijose/jacoco-fix` |
| `jojijose/netconf-frame-assembler` | `jojijose/add-tests` |
| `jojijose/ssh-async-read` | `jojijose/coverage-improvement` |

If a poorly-named branch was created, rename it immediately before doing any other work:
```bash
git branch -m jojijose/bad-name jojijose/good-name
```

#### Create or check out the branch (idempotent)

If **`jojijose/<new-branch-name>` already exists** locally or on **`origin`**, **check it out only** — **do not** create another branch with the same name.

```bash
BR=jojijose/async-event-readstream          # ← set to your functionality name
git fetch origin 2>/dev/null || true
if git show-ref -q --heads "$BR"; then git checkout "$BR"
elif git show-ref -q "refs/remotes/origin/$BR"; then git checkout -b "$BR" "origin/$BR"
else git checkout -b "$BR"
fi
```

Confirm with `git branch --show-current` before continuing.

Then continue with **inspect commits** / `merge-base` / `history.diff` / `gradle7 deltaCoverage` below.

### 1) Inspect recent commits

```bash
git log --oneline -n 5
```

Use this to see **where your branch left `master` / `origin/master`** (the mainline tip you diff against).

### 2) Choose the baseline commit `BASE`

- **Preferred (automatic):** same as “everything on this branch since mainline”:

  ```bash
  BASE=$(git merge-base HEAD origin/master 2>/dev/null || git merge-base HEAD master)
  echo "$BASE"
  ```

  Example: two feature commits on top of `origin/master` at `04f067a` → `merge-base` is `04f067a` (the corrected baseline in that scenario — **not** `HEAD` / the first line of the log).

- **Manual override:** if `merge-base` is wrong (rebase, unusual remotes), pick the commit from the log line that includes **`(origin/master, …)`** or **`(master, …)`** — that SHA is `BASE`.

- **Single commit on top of mainline:** `merge-base` still resolves to mainline tip; equivalent to diffing all branch work in one shot.

### 3) Regenerate `history.diff` (repo root)

Working tree + index vs `BASE` (includes uncommitted edits):

```bash
git diff "$BASE" > history.diff
```

**Committed only** (compare `BASE`..`HEAD`, no unstaged noise):

```bash
git diff "$BASE" HEAD > history.diff
```

Use whichever matches how you validate before push; re-run the same command **after** adding tests or production fixes.

### 4) Run delta coverage

```bash
gradle7 deltaCoverage
```

### 5) If the build fails on a coverage rule

Example:

`Rule violated for bundle shared-ssh-client: branches covered ratio is 0.5, but expected minimum is 0.7`

- Add or extend **unit tests** so changed branches in the delta are covered (typical target **≥ 0.7** branch ratio for the named bundle — follow the exact threshold in the error).
- Go back to **step 3** (refresh `history.diff`) then **step 4** (`gradle7 deltaCoverage`).

### 6) Bounded retries — no endless loop

- Allow at most **3** fix-and-rerun cycles **after** the first failing `deltaCoverage` (i.e. **≤ 4** `gradle7 deltaCoverage` runs for the same change-set before stopping).
- If it **still** fails after that, **stop**: report the full rule line (bundle, metric, actual vs expected), what tests were added, and leave the remainder for human follow-up. **Do not** keep iterating blindly.

---

## New or test (`testImplementation`) dependencies — Jenkins and approval

Before adding **any** new Maven coordinates (especially `testImplementation`, `testRuntimeOnly`, Mockito, Byte Buddy, SSHD test jars, etc.):

### 1) Search the org codebase for an already-approved version

Use the internal search (Orbweb / code search). Query format (adjust `q=` for `groupId:artifactId` or full GAV; patch version can be broadened to see what is already in use):

```text
http://orbw-web.ca.alcatel-lucent.com:6080/?q=net.bytebuddy%3Abyte-buddy-agent%3A1.14&i=nope&literal=nope&files=&excludeFiles=&repos=
```

- Prefer a **version already present** in another MDM or NMS `build.gradle` / BOM / catalogue so Jenkins and third-party review stay aligned with the fleet.
- If the search shows several patch versions, pick the **newest patch that still matches** the stack you need (e.g. keep `byte-buddy` and `byte-buddy-agent` on the **same** release line Mockito expects).

### 2) Example alignment (from `shared-ssh-client` / similar test stacks)

```gradle
testImplementation 'org.mockito:mockito-core:4.11.0'
testImplementation 'net.bytebuddy:byte-buddy:1.14.18'
testImplementation 'net.bytebuddy:byte-buddy-agent:1.14.18'
```

After Orbweb lookup, **bump patch versions together** when a newer approved patch exists; do not introduce a random new `groupId:artifactId:version` that no other repo uses unless approval process explicitly allows it.

### 3) When a different library is objectively better

If a change **requires** a newer or alternate library (security fix, Java 17 module opens, Mockito inline, etc.), you may use it **after** confirming no suitable version already exists in-repo — then **report clearly** in the change summary or PR: what was added/changed, why, and the Orbweb evidence (or sibling `build.gradle` reference) used.

---

## On build failure

If the build ends with `BUILD FAILED`:

### 4a — Collect the failure details

```bash
gradle7 clean build 2>&1 | tee /tmp/build-out.txt
grep -E "^(FAILURE|error:|> Could not|> Task)" /tmp/build-out.txt | head -60
```

### 4b — Triage by failure category

| Symptom | Fix |
|---|---|
| `Rule violated for bundle … branches covered ratio` / `deltaCoverage` | Regenerate `history.diff` from correct `BASE` (`merge-base` with `origin/master`), add UTs for uncovered branches, rerun `gradle7 deltaCoverage` (see **Delta coverage**; stop after bounded retries). |
| `error: cannot find symbol` / `package X does not exist` | Missing or wrong dependency in `build.gradle` — add/update the `implementation`/`compileOnly` line |
| `Could not resolve com.example:artifact:version` | Dependency version mismatch or missing repo — check `repositories` block and version catalogue |
| `Could not find method compile()` | Legacy `compile` config — replace with `implementation` or `api` |
| `Could not find method runtime()` | Replace with `runtimeOnly` |
| `Could not find method bundle()` | Bnd plugin missing — add `apply plugin: 'biz.aQute.bnd.builder'` or skip the manifest→bundle transform |
| `Checkstyle` violation | Fix the reported style issue in the flagged file, or suppress with `// CHECKSTYLE:OFF` |
| `Test` task failure | Read test report under `build/reports/tests/test/index.html`; fix failing test or the production code it exercises |
| `Execution failed for task ':jar'` | Check `bnd.bnd` or manifest section in `build.gradle` for missing exports/imports |

### 4c — Apply the fix

Edit the relevant file(s). For `build.gradle` changes, mirror a **working sibling repo** and Orbweb-approved versions.

### 4d — Rebuild

In the **same** shell session (same repo `cd`), run:

```bash
gradle7 clean build
```

Repeat 4a–4d until `BUILD SUCCESSFUL`.

---

## Common repos and paths

| Repo name | Path |
|---|---|
| `md-deployer-worker` | `/c/NSP/MDM/md-deployer-worker` |
| `md-restconf-app` | `/c/NSP/MDM/md-restconf-app` |
| `md-config-core` | `/c/NSP/MDM/md-config-core` |
| `shared-md-db-yang` | `/c/NSP/MDM/shared-md-db-yang` |
| `shared-md-mediation-core` | `/c/NSP/MDM/shared-md-mediation-core` |
| `mdm-core-netconf` | `/c/NSP/MDM/mdm-core-netconf` |
| `shared-ssh-client` | `/c/NSP/MDM/shared-ssh-client` |
| `shared-netconf-client` | `/c/NSP/MDM/shared-netconf-client` |

---

## Notes

- `gradle7` is the project-specific Gradle wrapper alias; do not use plain `gradle` or `./gradlew` unless the repo documents otherwise. For full builds use **`gradle7 clean build`**, or **`gradle7`** when `defaultTasks` already runs `clean` and `build` (or equivalent).
- Java 17 must be sourced for **each new** Bash process; a single long-lived Bash session only needs `source` once.
- Agents should use **`bash.exe -lc "…"`** from PowerShell (see above), not assume `gitbash` is defined in the tool environment.
- For build.gradle transform patterns across repos, see the `gradle-mdm-java-upgrade` skill.
