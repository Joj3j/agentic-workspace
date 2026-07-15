---
name: build-go-repo
description: Builds Go repos that use the `.go-make` CI pipeline submodule (`make build`, tests,
  delta coverage). Regenerates `history.diff` from the Jenkins `[jenkins]` baseline or merge-base,
  runs tests with `gocover-cobertura`, and checks delta coverage via `docker run
  build-unittest-coverage-delta:1`. Adds tests until the threshold passes (bounded retries; stop
  and report if still failing). Use when building any Go repo that contains a `.go-make` directory,
  fixing delta coverage failures, or running `make delta-coverage` locally.
---

# Build Go Repo (`.go-make` pipeline)

## Identifying a `.go-make` repo

This skill applies to any Go repo that contains a `.go-make/` submodule directory at its root.
That directory holds `go.mk`, which provides `make build`, `make test`, `make delta-coverage`, and
related CI targets.

```bash
# Check from the repo root:
ls .go-make/go.mk && echo "uses .go-make pipeline"
```

If `.go-make/` is absent, the repo uses a custom or internal Makefile — fall back to `make build`
/ `make test` (or the repo's documented workflow) without the delta-coverage steps below.

---

## Agent policy — run builds without asking

When this skill applies: **invoke `make build`, `make test`, `make coverage-check`, or focused
`go test ./internal/...` commands as often as needed** without asking permission. **Only ask
before `git commit` or `git push`** (unless the user already instructed that).

After code changes, regenerate `history.diff` and run delta coverage. Only stop and report if the
tool refuses (then describe the error).

---

## Build commands

```bash
make build          # compile the binary
make test           # run all unit tests
make coverage-check # tests + simple line-coverage check (tools/coverage-check.go)
```

Local test run without make:

```bash
GOSUMDB='sum.golang.org' GONOSUMDB='*' go test -count=1 ./internal/<pkg>/...
```

Use the `GOSUMDB` / `GONOSUMDB` overrides — `go.mk` sets them and bare `go test` may fail
checksum validation without them.

---

## Delta coverage (`history.diff` + `make delta-coverage`)

Jenkins enforces **delta coverage** on every MR: the percentage of *changed* lines covered by
tests must meet the repo's threshold (check the build log for the exact value; typical: 70%).

### Agent policy — run delta coverage without asking

Run the full workflow (steps 1–4) **as often as needed** to reach the threshold.
Maximum **4 attempts** before stopping and reporting.

### 1) Find the diff baseline

**Jenkins baseline** (matches CI exactly):

```bash
BASE=$(git log --grep='\[jenkins\]' --pretty=format:'%h' | head -1)
echo "Jenkins base: $BASE"
```

**Merge-base** (preferred when scoping to branch-only changes):

```bash
BASE=$(git merge-base HEAD origin/master 2>/dev/null || git merge-base HEAD master)
```

Use whichever matches what Jenkins reports in the build log. Confirm scope with
`git diff "$BASE" --stat`.

### 2) Regenerate `history.diff` (repo root)

```bash
git diff "$BASE" > history.diff          # includes uncommitted edits
# or committed-only:
git diff "$BASE" HEAD > history.diff
```

> **Never commit `history.diff`** — regenerate on demand.

### 3) Run tests and generate Cobertura XML

```bash
# Packages that have test files (matches COVERAGE_PKGS in Makefile)
COVERAGE_PKGS=$(find internal -name '*_test.go' | xargs -I{} dirname {} | sort -u | sed 's|^|./|' | tr '\n' ' ')

GOSUMDB='sum.golang.org' GONOSUMDB='*' \
  go test -count=1 -coverprofile=coverage.out -covermode=atomic $COVERAGE_PKGS

# Convert to Cobertura XML (install once: go install github.com/t-yuki/gocover-cobertura@latest)
mkdir -p build/test-results/test/cobertura
gocover-cobertura < coverage.out > build/test-results/test/cobertura/coverage.xml
```

If the `Makefile` overrides `GO_COBERTURA_TEST_CMD` or `COVERAGE_PKGS`, follow that instead.

### 4) Run delta coverage

```bash
# Via make (uses podman on CI):
make delta-coverage

# If podman is absent locally, use docker directly:
docker run --rm \
  -v $(pwd):/app/data/ \
  orbw-artifactory.ca.alcatel-lucent.com:8081/nokia-nsp-docker-local/build-unittest-coverage-delta:1 \
  data/history.diff data/build/test-results/test/cobertura/coverage.xml
```

### Interpreting results

**Pass:**
```
100% of changes covered
```
or any percentage ≥ threshold.

**Fail:**
```
uncovered: 20, delta: 32
37.5% of changes covered
Threshold of 70 not passed, failing
```

---

## If delta coverage fails — add tests

The delta-coverage tool only measures **lines present in `history.diff`** — not total file
coverage. Always work from the diff first, then find which of those new lines are uncovered.

### Step 1 — identify uncovered delta lines

```bash
# For each file reported as < 1.0 in the delta-coverage output:
git diff "$BASE" -- path/to/file.go | grep '^+' | grep -v '^+++'   # new lines in diff
grep "path/to/file.go" coverage.out | grep ' 0$'                    # uncovered blocks
```

Cross-reference the line numbers from `coverage.out` (`file.go:L1,L2 N 0`) against the `+`
lines in the diff. Only blocks that appear in **both** lists need new tests.

### Step 2 — scope the coverage run to changed packages only

Run `go test` only over packages that contain the changed files to keep coverage.out clean:

```bash
# Derive from the diff automatically:
COVERAGE_PKGS=$(git diff "$BASE" --name-only | grep '\.go$' | xargs -I{} dirname {} \
  | sort -u | sed 's|^|./|' | tr '\n' ' ')

GOSUMDB='sum.golang.org' GONOSUMDB='*' \
  go test -count=1 -coverprofile=coverage.out -covermode=atomic $COVERAGE_PKGS
```

### Step 3 — write tests for exactly the uncovered new lines

#### 3a. New functions in the delta

When a new function appears in the diff, always add at least one test that calls it directly.
Identify every new function signature in the diff:

```bash
git diff "$BASE" | grep '^+func '
```

For each new function, the test must:
- Call the function with representative inputs
- Assert the return values or side-effects
- Cover every branch inside the function that is also in the diff (use the `coverage.out` cross-
  reference from Step 1 to find which branches are still uncovered after the basic call)

Example workflow — diff shows `+func Validate(x Foo) error`:

```bash
# 1. Identify the new function
git diff "$BASE" | grep '^+func '
# → +func Validate(x Foo) error

# 2. Check which blocks inside it are uncovered
grep "validate.go" coverage.out | grep ' 0$'
# → validate.go:42,45 1 0   ← the error-return branch

# 3. Add tests: one for the happy path, one that triggers the uncovered branch
func TestValidate_Valid(t *testing.T)   { ... }   // covers the function entry
func TestValidate_Invalid(t *testing.T) { ... }   // covers line 42-45
```

#### 3b. New parameters or fields added to existing functions

When an existing function gains a new parameter or struct field in the diff, existing tests
may still pass but leave the new parameter's code paths uncovered. Identify these:

```bash
# Find changed function signatures (lines with +func or +\t<FieldName>):
git diff "$BASE" | grep '^+' | grep -v '^+++' | grep -E '^\+func |\+[[:space:]]+[A-Z][a-zA-Z]+'
```

For each new parameter/field:
- If it is a **callback / func field**: add a test that passes a non-nil value and verifies it
  is invoked. Use a channel or captured variable to assert the call happened.
- If it is a **flag / bool**: add a test with it set to `true` AND one with `false` if both
  paths are in the diff.
- If it is a **variadic opts slice** (`...Option`): add a test that passes at least one option
  so the `for range` loop body executes.
- If it is a **struct field with a conditional guard** (`if field != nil { ... }`): add a test
  that constructs the struct with the field populated.

#### 3c. Pattern reference table

| New code shape | What to test |
|---|---|
| `+func Foo(...)` new function | Direct unit test; cover all branches also in the diff |
| New parameter added to existing func | Test that exercises the new parameter's code path |
| `if cond { ... }` guard | Test that makes `cond` true |
| `if err != nil { return err }` error path | Inject a failing input or mock |
| Returned closure / inner `func` literal | Call the returned closure; assert its side-effects |
| `for _, o := range opts { o(&x) }` opts loop | Call the variadic function with at least one option |
| `if field != nil { use(field) }` optional field | Set the field to a non-nil value in the test |
| `go cb(...)` goroutine dispatch | Buffered channel in callback; `select` with a timeout |
| `switch` / `case` branch | Drive each uncovered case value |

### Step 4 — confirm delta lines are now covered

After adding tests, regenerate coverage and re-run the delta check:

```bash
gocover-cobertura < coverage.out > build/test-results/test/cobertura/coverage.xml
docker run --rm \
  -v $(pwd):/app/data/ \
  orbw-artifactory.ca.alcatel-lucent.com:8081/nokia-nsp-docker-local/build-unittest-coverage-delta:1 \
  data/history.diff data/build/test-results/test/cobertura/coverage.xml
```

If still failing, repeat Step 1 to identify remaining uncovered delta lines — do not add tests
for lines that are already covered or that are not in the diff.

### Avoid nil-client hangs in tests

When a cache or client method calls a network backend when data is absent, passing `nil` for the
client will panic or hang. Pre-populate the cache so the method returns early:

```go
// Example: seed an entry so EnsureRootMeta returns early (no schema-server call)
cache.UpsertEntry(&pkg.Entry{
    Name:      "MySchema",
    Version:   "1.0.0",
    RootPaths: []string{"module:/root"}, // must be non-empty to prevent network fetch
})
```

If the "empty data" warning branch can only be triggered by reaching the network call, test it
in the package that owns the logic (same-package test with direct struct access) rather than
from an integration test that requires a live client.

### Bounded retries

Allow at most **4** `delta-coverage` runs per change-set. If still failing after that, **stop**:
report the exact output (uncovered count, delta count, percentage, threshold), what tests were
added, and leave the rest for human follow-up.

---

## On build failure

```bash
make build 2>&1 | tee /tmp/build-out.txt
grep -E "^#|error:|cannot find|undefined" /tmp/build-out.txt | head -40
```

| Symptom | Fix |
|---|---|
| `undefined: Foo` / `cannot find symbol` | Missing import or wrong package path |
| `imported and not used` | Remove the unused import |
| `cannot use nil as type` | Use `[]string{}` instead of `nil` for slice fields |
| `go test` hang | Check for nil pointer on nil clients; pre-populate state in tests |
| `delta-coverage` threshold not met | Add tests for uncovered changed lines (see above) |
| `podman: No such file or directory` | Use `docker run` directly instead of `make delta-coverage` |
| Proto `pb.go` out of date | Run `make proto` or `make generate` |
| `unrecognized import path "..."` | Module not reachable via proxy; enable the `replace` directive in `go.mod` pointing to a local clone. Verify the relative path resolves correctly with `ls <path>`. |
| `replacement directory ... does not exist` | The `replace` path depth is wrong. Resolve from the module's own directory, not the workspace root. |
| `cannot use X as type Y` after version bump | A type moved to an `internal` package and is no longer importable externally. Simplify the public API to not expose internal types (e.g. change a callback parameter from a struct type to a primitive). |

---

## Notes

- The Go module path is in `go.mod`; use it for import paths in new test files.
- `COVERAGE_PKGS` restricts coverage to packages that have `*_test.go` files to avoid empty
  coverage errors from untested packages.
- `gocover-cobertura` converts Go's `coverage.out` to Cobertura XML needed by the
  delta-coverage container: `go install github.com/t-yuki/gocover-cobertura@latest`.
- `history.diff` must **never be committed** to the branch.
- CI uses `podman`; locally `docker` is the fallback when podman is absent.
