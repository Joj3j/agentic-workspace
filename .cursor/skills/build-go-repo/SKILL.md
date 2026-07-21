---
name: build-go-repo
description: Builds Go repos that use the `.go-make` CI pipeline submodule (`make build`, tests,
  delta coverage). Runs CI-parity delta coverage via `delta_coverage_check.sh` (BUILDER=docker
  make test + delta container; **≥75% local target**, Jenkins gate is 70%). Never use host
  gocover-cobertura or coverage-check as a delta substitute. Adds unit tests for uncovered
  delta lines until the check passes (bounded retries). Use when building any Go repo with
  `.go-make/`, fixing delta coverage failures, or validating before Jenkins.
---

# Build Go Repo (`.go-make` pipeline)

## Identifying a `.go-make` repo

This skill applies to any Go repo that contains a `.go-make/` submodule directory at its root.
That directory holds `go.mk`, which provides `make build`, `make test`, `make delta-coverage`, and
related CI targets.

```bash
ls .go-make/go.mk && echo "uses .go-make pipeline"
```

If `.go-make/` is absent, fall back to `make build` / `make test` without delta-coverage steps.

---

## Agent policy — run builds without asking

Invoke `make build`, `make test`, and **CI-parity delta coverage** as often as needed without
asking permission. **Only ask before `git commit` or `git push`** (unless the user already
instructed that).

**Before declaring delta coverage OK**, always run `delta_coverage_check.sh` and confirm
**≥75%** of changed lines are covered (5-point buffer over Jenkins' 70% gate). Do **not** rely
on `make coverage-check` or a host-side `gocover-cobertura` run.

**When delta coverage fails:** add unit tests for every file the script lists with ratio `< 1.0`,
re-run the script, and repeat until ≥75% (max 4 attempts per change-set).

---

## CI-parity delta coverage (required before push)

Jenkins enforces **delta coverage** on changed lines (gate **70%**). Local validation must
mirror Jenkins exactly **and** target **≥75%** so margin exists before CI runs.

### One-command check (preferred)

From the repo root (or pass the repo path):

```bash
bash workspace-settings/.cursor/scripts/build-go-repo/delta_coverage_check.sh
# or
bash workspace-settings/.cursor/scripts/build-go-repo/delta_coverage_check.sh /path/to/repo
```

The script:

1. Sets `BUILDER=docker` (podman is not used locally when absent)
2. Regenerates `history.diff` from `git log --grep='\[jenkins\]'`
3. Runs `make test` (same as Jenkins: `gotestsum -coverpkg=./... ./...` in build image)
4. Verifies cobertura filenames use **relative** paths (`internal/...`), not module paths
5. Runs `build-unittest-coverage-delta:1` via docker

Exit 0 = ≥75% delta coverage (safe to push). Exit 1 = add unit tests for files listed with
ratio `< 1.0`, then re-run.

### Why local checks often lied (read this)

| Mistake | Symptom | Jenkins result |
|--------|---------|----------------|
| Host `gocover-cobertura` after `go test` | Delta reports **100%** | **Fails** (~25% on comm-worker-gnmi-go) |
| `make coverage-check` only | Per-package 80% line check passes | Delta still fails |
| `go test` on `COVERAGE_PKGS` without `-coverpkg=./...` | Wrong coverage scope | Mismatch |
| `find … '*_test.go'` for packages | Skips untested packages | Mismatch |
| Merge-base instead of `[jenkins]` baseline | Wrong diff scope | Mismatch |

**Root cause of false 100%:** Host `gocover-cobertura` writes filenames like
`nsp.nokia.com/comm/my-repo/internal/foo.go`. Jenkins build image writes `internal/foo.go`.
`history.diff` uses `internal/...`. The delta container **does not match** module-prefixed
filenames and incorrectly reports 100% covered.

**Fix:** Always let `make test` run `gocover-cobertura` **inside** the `orbw-build-go*` Docker
image (`BUILDER=docker make test`). Never convert `coverage.out` with host `gocover-cobertura`.

### Local-only debug changes (exclude from delta / UT)

When the user has **uncommitted local debugging** edits (log-level tweaks, temporary behavior
flags, `//NOT for COMMIT` guards) that must **not** ship on the branch:

1. **Stash or revert** those paths before regenerating `history.diff` or adding unit tests.
2. **Do not** write UTs to cover debug-only lines — they are out of CI scope once stashed.
3. Re-run `delta_coverage_check.sh` on the **remaining** branch diff only.

```bash
# Example: stash named local-debug edits, then validate the real branch delta
git stash push -m "local debug" -- path/to/debug_file.go ...
bash workspace-settings/.cursor/scripts/build-go-repo/delta_coverage_check.sh
```

Restore after validation with `git stash pop` when continuing local dev.

### Manual CI-parity steps (if script unavailable)

```bash
export BUILDER=docker
cd /path/to/repo

BASE=$(git log --grep='\[jenkins\]' --pretty=format:'%h' -1)
echo "Jenkins base: $BASE"
git diff "$BASE" > history.diff

make test   # must succeed; produces build/test-results/test/cobertura/coverage.xml

# Sanity: filenames must be relative, NOT module-qualified
grep -m1 'filename=' build/test-results/test/cobertura/coverage.xml
# good: filename="internal/app/foo.go"
# bad:  filename="nsp.nokia.com/comm/.../internal/app/foo.go"

docker run --rm \
  -v "$(pwd)":/app/data/ \
  orbw-artifactory.ca.alcatel-lucent.com:8081/nokia-nsp-docker-local/build-unittest-coverage-delta:1 \
  data/history.diff data/build/test-results/test/cobertura/coverage.xml
```

`make delta-coverage` is equivalent when `BUILDER=docker` is set (uses docker, not podman).

> **Never commit `history.diff`** — regenerate on demand.

---

## Build commands

```bash
export BUILDER=docker   # when podman is absent
make build              # compile via docker-build
make test               # CI-equivalent tests + cobertura XML
```

Local focused test (no delta validation):

```bash
GOSUMDB='sum.golang.org' GONOSUMDB='*' go test -count=1 ./internal/<pkg>/...
```

`coverage-check` (`tools/coverage-check.go`, per-package line threshold) is **not** delta
coverage. Run it only when explicitly asked; it does not gate Jenkins delta coverage.

---

## If delta coverage fails — add tests

The delta tool only measures **lines present in `history.diff`**. Work from the diff first.

### Step 1 — identify uncovered delta files

From `delta_coverage_check.sh` output, files with ratio `0.0` or `< 0.75` need tests. Example
failure pattern:

```
internal/app/grpc_server/grpc_server.go, 0.0
internal/app/grpc_server/notification_worker.go, 0.0
internal/system/system.go, 0.39
uncovered: 912, delta: 1224
25.49% of changes covered
Threshold of 70 not passed, failing
```

### Step 2 — map uncovered lines

```bash
BASE=$(git log --grep='\[jenkins\]' --pretty=format:'%h' -1)

# New/changed lines in a failing file:
git diff "$BASE" -- path/to/file.go | grep '^+' | grep -v '^+++'

# After BUILDER=docker make test, inspect coverage.out in repo root:
grep "path/to/file.go" coverage.out | grep ' 0$'
```

Cross-reference diff `+` line numbers with `coverage.out` blocks ending in ` 0`.

### Step 3 — write tests for uncovered delta lines

#### New functions (`+func Foo`)

```bash
git diff "$BASE" | grep '^+func '
```

Each new function needs a direct unit test covering every branch that appears in the diff.

#### New parameters / struct fields / callbacks

| Shape in diff | Test |
|---|---|
| `+func Foo(...)` | Direct unit test; all diff branches |
| New callback / `func` field | Pass non-nil; assert invoked (channel) |
| `if field != nil { ... }` | Construct with field set |
| `go cb(...)` | Buffered channel + `select` timeout |
| Entire new file (e.g. gRPC handler) | New `*_test.go` in same package |

Packages with **no** `*_test.go` (e.g. new `notification_worker.go`) always fail delta
coverage until tests are added — indirect coverage from other packages is not enough when
paths match correctly.

### Step 4 — re-run until ≥75%

```bash
bash workspace-settings/.cursor/scripts/build-go-repo/delta_coverage_check.sh
```

Confirm output shows `PASS: delta coverage OK (≥75%, threshold 75%)`. Maximum **4** attempts
per change-set.

### Avoid nil-client hangs in tests

Pre-populate caches so methods return early without network calls. See prior examples in
`internal/` test files that seed schema entries before `EnsureRootMeta`.

---

## On build failure

```bash
export BUILDER=docker
make build 2>&1 | tee /tmp/build-out.txt
grep -E "^#|error:|cannot find|undefined" /tmp/build-out.txt | head -40
```

| Symptom | Fix |
|---|---|
| Delta 100% locally, Jenkins fails | Host cobertura paths; use `BUILDER=docker make test` |
| `podman: No such file or directory` | `export BUILDER=docker` |
| `coverage-check` passes, delta fails | Different checks; run `delta_coverage_check.sh` |
| Proto `pb.go` out of date | `make proto` |
| `unrecognized import path` | Add `replace` in `go.mod` to local clone |

---

## Notes

- Module path: `go.mod` first line.
- Jenkins baseline: `git log --grep='\[jenkins\]' --pretty=format:'%h' | head -1` then
  `git diff $BASE > history.diff` (matches Jenkins `git diff <jenkins-sha>`).
- Jenkins test command (in `go.mk`): `gotestsum … -coverprofile=coverage.out -coverpkg=./... ./...`
  then filter `.pb.go`, `test`, `metrics` from coverage before cobertura.
- `history.diff` must **never** be committed.
