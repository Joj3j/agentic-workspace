---
name: mr-review
description: >-
  Produces a severity-classified Merge Request review report from a GitLab MR URL or
  local branch reference. Reads the diff via git (local clone, SSH access required for
  fetch), identifies the topic domain from changed files (doc / code / test / config),
  pulls relevant repo markups (HLD, LLD, existing source files), and asks the user for
  functional context. Classifies findings as major, minor, or info. Writes the report
  to docs/ in the target repo and outputs a summary. Use when the user provides a
  GitLab MR URL or says "review MR", "review this branch", or "review this diff".
---

# MR Review

Produce an evidence-based, severity-classified review of a GitLab Merge Request.

## Step 1 — Resolve the MR diff

Determine the diff source in this order:

**A. Branch already fetched locally** (preferred — no network required):

```bash
cd <repo>
git log --oneline origin/master..origin/<branch> 2>/dev/null
git diff origin/master...origin/<branch> --stat
```

**B. Fetch from remote** (requires SSH access to GitLab):

```bash
cd <repo>
git fetch origin <branch>           # e.g. sgang/perf_testing
git diff origin/master...origin/<branch> --stat
```

**C. From MR URL** — parse the URL to get project path and MR IID, then use the
GitLab REST API (requires a `GITLAB_TOKEN` env var):

```bash
# URL form: http://<host>/<namespace>/<project>/-/merge_requests/<iid>/diffs
GITLAB_HOST=orbw-git.ca.alcatel-lucent.com
PROJECT=sgang/nsp-schema-server   # from URL
MR_IID=36

curl -s -H "PRIVATE-TOKEN: $GITLAB_TOKEN" \
  "https://$GITLAB_HOST/api/v4/projects/$(python3 -c "import urllib.parse; print(urllib.parse.quote('$PROJECT', safe=''))")/merge_requests/$MR_IID/diffs" \
  | python3 -c "import json,sys; [print(d['diff']) for d in json.load(sys.stdin)]"
```

If neither approach works, ask the user to paste the diff or key files directly.

## Step 2 — Identify topic domain

From the list of changed files, classify the MR:

| Changed paths | Domain |
|---------------|--------|
| `docs/` only | **Design/Plan document** |
| `*.go` (non-test) | **Implementation** |
| `*_test.go` | **Test coverage** |
| `kustomize/`, `*.yaml` config | **Deployment/Config** |
| `proto/`, `*.proto` | **API contract** |
| Mixed | List all domains |

Adjust review depth per domain — see [REVIEW_DOMAINS.md](REVIEW_DOMAINS.md).

## Step 3 — Read repo context

For the changed repo, read in parallel:

- `docs/HLD/01-architecture-overview.md` (or `docs/HLD/CODEBASE_OVERVIEW.md`)
- HLD chapters relevant to the MR topic (e.g. `09-platform-considerations.md`,
  `10-resource-usage.md` for performance MRs)
- Any LLD docs referenced by or related to the changed files
- Source files directly touched by the diff
- Existing tests in the same package or feature area

Use semantic search on the repo to find additional related files when the diff is
small but cross-cutting.

## Step 4 — Ask for functional context

Ask the user (via `AskQuestion` or conversationally) about:

1. **Topic / domain**: What is the MR about? (Confirm or refine what you inferred.)
2. **Functional background**: Are there related tickets, Confluence pages, or LLD
   docs not in the repo that define requirements?
3. **Known constraints**: Are there SLOs, hardware limits, vendor compatibility
   requirements, or support policies (e.g. N-3 release support) that apply?
4. **Scope**: Should the review cover only the changed files, or also impact on
   downstream consumers (other repos in the workspace)?

For the NSP workspace, typical context to ask about:
- Which NSP services consume this component (comm-layer-server, comm-worker-gnmi-go,
  comm-worker-netconf-rs, comm-dispatcher)?
- Which RPC methods are on the critical path of those consumers?
- What is the supported vendor/version matrix (SRL, SR OS, Cisco XR, Juniper)?
- Is N-3 release support required for schema/model compatibility?

## Step 5 — Review by domain

### Design / Plan document review

Check each of these dimensions if the document touches them:

| Dimension | Key questions |
|-----------|---------------|
| **Completeness** | Are all deliverables listed? Do referenced files exist? |
| **Schema loading variants** | Are all ingest paths covered (Create, Upload-seq, Upload-concurrent, Reload, URL-based)? |
| **Vendor/version matrix** | Are all supported vendors present (Nokia SRL, SR OS, Cisco XR, Juniper)? Is N-3 versioning addressed? |
| **Worst-case paths** | Is `GetSchema(path="/")` + `with_full_details=true` tested? Is root ExpandPath tested? |
| **HA / DR** | Pod restart under load? Warm restart from persistent store? Readiness probe alignment? |
| **Concurrency model** | Lock scope documented? Writer-starvation from long read holds analyzed? |
| **Thundering herd** | Are startup scenarios tested with K concurrent consumers? |
| **Message size ceilings** | Is response size compared against `MaxCallRecvMsgSize`? |
| **Pass/fail thresholds** | Are SLOs defined for ALL tested RPCs (not just primary ones)? |
| **CI portability** | Are fixture paths env-variable-driven? Is a fixture setup runbook present? |
| **Regression gate** | Is a comparison tool (e.g. `benchstat`) identified? |

### Implementation / Code review

Check:
- Lock scope: are expensive operations (YANG parse, proto serialization) inside or
  outside the critical lock section?
- Error handling: are retriable gRPC codes handled (Unavailable, DeadlineExceeded)?
- Context propagation: are `ctx.Err()` checks present in long loops?
- Test coverage: are new code paths covered by unit or integration tests?
- Metric counters: are new RPCs instrumented?

### Test review

Check:
- Do benchmarks use `b.ResetTimer()` correctly?
- Are memory stats captured with `runtime.ReadMemStats` before AND after?
- Are goroutine leak checks present (`runtime.NumGoroutine` delta)?
- Are hardcoded addresses / paths env-variable-driven?
- Is the `-tags` build tag documented in the README?

## Step 6 — Produce the report

Write the report to `docs/perf-testing/REVIEW_MR<IID>.md` (for perf MRs) or an
appropriate path in the target repo. Use this structure:

```markdown
# MR !<IID> — <Title>: Review

**MR:** `<namespace>/<project>!<IID>`
**Branch:** `<branch>` → `<target>`
**Nature:** <domain(s)>

---

## R-01 · <Short title> [major|minor|info]

<Evidence-based finding. Quote or reference the specific section/file/line.>

**Review:** <Specific, actionable request to the author.>

---

## Summary Table

| ID | Finding | Severity |
|----|---------|----------|
| R-01 | ... | major |
```

Severity definitions:
- **major** — must be addressed before merge or requires a follow-up ticket
- **minor** — should be addressed; acceptable to defer with acknowledgement
- **info** — optional improvement, no action required

### Writing findings for good pending comments

Each R-NN section becomes one GitLab pending comment. The comment posts:
- The heading as the title line (`🔴 ## R-01 · <title>`)
- The `**Review:** ` action as the body — write this as a clear, self-contained
  instruction the author can act on without reading the full report.
- If a finding has no `**Review:**` line, the description body is used instead.
  Ensure the description is also self-contained in that case.

### Pinning every finding to the document or code file under review

**All findings must be pinned to a specific line in the changed file.** Generic
(unanchored) notes are only acceptable when no changed file is relevant to the
finding.

**How to pin — mandatory step before writing findings:**

1. Fetch the MR diff and list the changed files and their line ranges:
   ```bash
   curl -s "http://<host>/api/v4/projects/<encoded-project>/merge_requests/<iid>/diffs" \
     -H "PRIVATE-TOKEN: $GO_GIT_PAT" | python3 -c "
   import json, sys, re
   for d in json.load(sys.stdin):
       n = 0
       for l in d['diff'].splitlines():
           if l.startswith('@@'): m=re.search(r'\+(\d+)',l); n=int(m.group(1))-1 if m else 0
           elif not l.startswith('-'): n+=1
           if l.startswith('+'): print(f\"{d['new_path']}:{n}  {l[1:].rstrip()}\")
   "
   ```
2. For each finding, identify the exact file and new-side line number where the
   issue is most visible (the table row, code line, or section heading it relates to).
3. Add the annotation **immediately after** the R-NN heading line in the report:

```markdown
## R-01 · Finding title [major]
<!-- file: docs/HLD/YANG1-1-rfc7950-compliance.md, line: 217 -->
```

**For new files (entire file is a diff):** every line number is valid — pin to the
table row, section heading, or code line the finding is about.

**For changed sections of existing files:** use the new-side line number from the
`git diff` or API output above.

**The script auto-detects lines** from content snippets as a fallback, but explicit
annotations are always more accurate and should be used for all findings in a
document or code review.

## Step 7 — Post findings to GitLab MR (after user confirms)

**Do not post automatically.** Present the preview table first and wait for explicit
user confirmation before calling any GitLab API.

Git access is already configured in the shell (SSH keys in place). The script
auto-detects `GITLAB_HOST` from the repo's git remote — no manual host config needed.
Only `GITLAB_TOKEN` must be provided. User is always **jojijose**.

### Default behaviour

- **Pending (draft) comments** — visible only to the reviewer until published.
  Open the MR in GitLab → "Pending comments" → **Submit review** to publish.
- **Comment format** — each comment contains:
  - Heading: `🔴 ## R-01 · <title>` (colour button + ID + title, no severity suffix)
  - Body: the **Review:** action text when present; falls back to the description body
    when the finding has no explicit review action (so no comment is ever left empty)
- **Auto diff-location** — the script fetches the MR diff and pins each finding to
  the most relevant changed line using snippet matching. Falls back to a general note
  when no match is found in the diff.

Use `--publish` to post as immediately visible comments.
Use `--full` to include the full description body even when a review action is present.

### Setup (one-time, token only)

`GO_GIT_PAT` is already set in the shell environment and is the GitLab PAT for
`jojijose` on `orbw-git.ca.alcatel-lucent.com`. Use it directly — no extra env file
needed:

```bash
export GITLAB_TOKEN="$GO_GIT_PAT"
```

### Preview (always run first — show table to user before posting)

```bash
GITLAB_TOKEN=$GO_GIT_PAT python3 \
  /home/joji/Go/workspace-settings/.cursor/scripts/mr-review/post_review.py \
  --review /path/to/REVIEW_MR<IID>.md \
  --mr-url http://<host>/<namespace>/<project>/-/merge_requests/<iid> \
  --dry-run
```

The preview table shows each finding's severity (with colour button), auto-detected
diff location (`file:line` or `general note`), and the posting mode. Show it to the
user and ask: *"Does this look right? Should I post these findings?"*

### Post (only after user explicitly confirms)

```bash
GITLAB_TOKEN=$GO_GIT_PAT python3 \
  /home/joji/Go/workspace-settings/.cursor/scripts/mr-review/post_review.py \
  --review /path/to/REVIEW_MR<IID>.md \
  --mr-url http://<host>/<namespace>/<project>/-/merge_requests/<iid>
# The script prompts "Post N findings? [y/N]" as a second gate.
```

Optional flags:

| Flag | Effect |
|------|--------|
| `--severities major,minor` | Post only major/minor; skip info |
| `--full` | Include full description + review action in each comment |
| `--publish` | Post as immediately visible comments (skip draft mode) |
| `--repo-dir /path/to/repo` | Override directory for git remote auto-detection |

### Pinning a finding to a specific diff line (explicit override)

The script auto-detects diff lines from finding content. To override or force a
specific line, add an HTML comment immediately after the R-NN heading:

```markdown
## R-05 · Test line should be removed [minor]
<!-- file: README.md, line: 24 -->
```

`line` is the line number **in the new version** of the file.

### Env variables

| Variable | Source | Description |
|----------|--------|-------------|
| `GITLAB_TOKEN` | Must be set (`$GO_GIT_PAT`) | Personal access token with `api` scope |
| `GITLAB_HOST` | Auto from git remote | GitLab hostname — override only if needed |

---

## Grounding rules

1. Only assert facts present in the diff, repo files, or user-provided context.
   For anything not verifiable, write an **open question** rather than a finding.
2. Do not invent latency numbers, memory figures, or RPC counts — only cite values
   from the code, config, or test files you have read.
3. Cross-reference source code when making concurrency or correctness claims
   (e.g. read `memstore.go` before claiming lock scope).
4. If a concern applies to one store backend but not another (e.g. memstore vs
   persiststore), state which backend explicitly.

## Additional resources

- See [REVIEW_DOMAINS.md](REVIEW_DOMAINS.md) for per-domain checklists.
- Reference MR: `sgang/nsp-schema-server!36` — perf plan review with 20 findings
  across all severity levels. Report at
  `nsp-schema-server/docs/perf-testing/REVIEW_MR36.md`.
- Test MR: `jojijose/workspace-settings!4` — use to validate posting; diff only
  touches `README.md` so findings unrelated to that file post as general notes.

## Posting learnings (from nsp-schema-server!35 and !36 reviews)

- **Draft notes API** — use `POST .../draft_notes` (not `.../discussions`) for
  pending comments; field is `note:` not `body:`. Publish via GitLab UI
  "Submit review" or `bulk_publish`.
- **Comment format that works** — heading with colour button + ID + title (no
  severity suffix in the title); then the review action directly without a
  "Review:" label prefix.
- **Fallback body** — when `**Review:**` is absent or the finding is abstract,
  use the description body so the comment is never empty and always actionable.
- **Always pin to the changed file** — all findings must be anchored to a specific
  line in the document or code file under review. Generic notes should be the
  exception, not the rule. Use the diff output to find line numbers, then add
  `<!-- file: path/to/file, line: N -->` after every R-NN heading.
- **New large files** — GitLab's diff API returns empty diff for very large new files
  (e.g. a 400-line doc). Auto-detection then fails. Always use explicit annotations
  for such files; the new-side line numbers are still valid for diff notes because
  all lines are added.
- **Auto diff-location** — fetches `GET .../diffs`, builds a `{file: [(line, content)]}`
  map, matches quoted/backtick snippets from the finding against changed lines.
  Explicit `<!-- file: ..., line: N -->` annotation always wins over auto-detection.
- **scheme handling** — private GitLab uses `http://`; the script reads the scheme
  from the MR URL and uses it for all API calls to avoid SSL errors.
- **Token** — `GO_GIT_PAT` in the shell env is the GitLab PAT; pass as
  `GITLAB_TOKEN=$GO_GIT_PAT`.
