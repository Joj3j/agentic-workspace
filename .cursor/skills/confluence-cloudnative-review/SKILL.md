---
name: confluence-cloudnative-review
description: >-
  Fetches a Confluence design or arch page by URL or page ID, then produces a
  cloud-native architecture review as structured markup. For NSP HLD-style pages,
  checks coverage against the arch-docs HLD section template (chapters 1–12). Classifies
  findings as critical, major, minor, info, or improvements; asks questions where the
  page is silent (no invented facts). Use when the user asks for a Confluence review,
  cloud-native review, HLD completeness check, design review from Confluence, or
  architecture feedback with severity levels.
---

# Confluence cloud-native design review

Produce an **evidence-based** cloud-native review of a Confluence page. **Only** assert facts that appear in the fetched content or in verifiable metadata (title, version). For anything not stated on the page, output **open questions** instead of guessing.

## When to use

- User provides a Confluence **URL** or **page ID** and wants architecture / design review comments.
- User wants review output as **markup** (Markdown) with **severity** buckets.

## Prerequisites

Follow [confluence-page](../confluence-page/SKILL.md) for env setup:

1. `cd agentic-workspace/.cursor/scripts/confluence && source confluence_env.sh`
2. If sourcing fails, tell the user to configure `confluence_env.local` from the example.

## Step 1 — Fetch the page

Parse URL or use page ID (same rules as confluence-page skill):

| URL pattern | Script args |
|-------------|-------------|
| `.../display/<SpaceKey>/<Page+Title>` | `--space-key <SpaceKey>` `--title "<decoded title>"` |
| `.../pages/viewpage.action?pageId=<ID>` | `--page-id <ID>` |

Run (default text is usually enough for review):

```bash
cd agentic-workspace/.cursor/scripts && source confluence_env.sh
python3 confluence_read_page.py --page-id <ID> --format text
# or
python3 confluence_read_page.py --title "..." --space-key NSPArchEvo --format text
```

On failure, report stderr and stop; do not fabricate page content.

Optional: use `--format html` only if diagrams/tables in HTML carry meaning lost in text.

## Step 2 — Grounding rules (no hallucination)

1. **Cite the page**: For each substantive comment, tie it to a **quoted phrase, section heading, or bullet** from the fetched content when possible. If you cannot point to text, label the item as a **question** or **assumption to confirm**, not a finding.
2. **CVEs and third-party issues**: Do **not** invent CVE IDs or claim a library is vulnerable unless the page names a **specific version** and you have **separate verified** data (e.g. user-supplied scan, or an explicit check the user asked you to run). Otherwise write: *"Page names the library but not the version — confirm with SBOM or scanner."*
3. **Numbers**: Do not invent latency, RPS, CPU, memory, or timing. If the page omits them, ask what targets or measurements exist.
4. **Unknowns**: Use a dedicated **Open questions** section for gaps; prefer *"Not described on page: …"* over speculation.

## Step 3 — Review dimensions (minimum)

Cover these **if the page touches them**; if the page is silent, add a **question** under Open questions instead of skipping silently.

| Area | Look for on page | If missing |
|------|------------------|------------|
| **Workload & resources** | requests/limits, QoS, HPA/VPA, PDB, node affinity/taint | Ask for classes and headroom |
| **Networking** | Services, ingress/gateway, mTLS, NetworkPolicy, east-west paths, timeouts | Ask how pods discover and authorize peers |
| **Latency & connectivity** | Sync vs async, retries, backoff, deadlines, regional layout | Ask for SLOs and critical path |
| **Caching & consistency** | What is cached, TTL, invalidation, source of truth, sync frequency | Ask staleness tolerance |
| **Data stores** | DB choice, pooling, query patterns, pagination/streaming, migrations, backups | Ask about hot queries and load shape |
| **Dependencies & supply chain** | Named libs/images, versions, upgrade policy, SBOM | Ask how CVEs are tracked (without inventing CVEs) |
| **Observability** | Metrics/logs/traces, SLOs, alerting | Ask what breaks user-visible behavior |
| **Security & ops** | Secrets, RBAC, IRSA/workload identity, upgrades, DR | Ask who can do what at runtime |

For a **longer checklist** (resilience, storage, CI/CD, compliance, etc.), read [reference.md](reference.md) and fold in items relevant to the page.

### HLD / Confluence template coverage (arch pages)

When the page is an **NSP architecture / HLD-style** Confluence doc (or clearly intended as such), compare fetched headings and body to the **canonical section list** (same as `arch-docs/docs/HLD/index.md` and Confluence template pageId 2162422282):

1. Architecture Overview  
2. Components  
3. Key FOSS/3PP Components  
4. System Dependencies  
5. APIs  
6. Models  
7. Data Flow  
8. Security and Access Control  
9. Platform Considerations  
10. Resource Usage  
11. Patents  
12. Sign-Off  

**Rules:**

- Treat synonymous headings as covered (e.g. "Third-party dependencies" ≈ FOSS/3PP).
- For each **missing** or **empty** section, add an item under **Minor** or **Info** (use **Major** if governance or safety expects that section for production sign-off — e.g. no Security or Platform at all).
- If the page is **not** an arch template doc, skip this subsection or state "Not applicable: not an HLD-style page."

Include a dedicated section in the output (see Step 5 template): **HLD template coverage** — table or bullet list: section → Present / Partial / Missing.

**Cross-skill:** Section expectations when **authoring** are defined in [create-repo-arch-doc](../create-repo-arch-doc/SKILL.md) ("Confluence body and HLD section coverage").

## Step 4 — Severity definitions

Use **exactly one** severity per item:

| Severity | Meaning |
|----------|---------|
| **critical** | Could cause outage, data loss, security breach, or unrecoverable state if built as described; or a mandatory control is missing where the page claims production use. |
| **major** | Significant reliability, security, or operability risk; likely production pain without mitigation. |
| **minor** | Improvement with limited blast radius; clarity or consistency issues. |
| **info** | Neutral observation, context, or alignment note. |
| **improvements** | Optional enhancement (cost, DX, future-proofing) — not required for safe launch. |

If severity depends on unknowns, use **info** or **open question** until clarified.

## Step 5 — Output format (markup)

Emit **Markdown** using this template. Keep each finding **one short paragraph** plus optional bullets; end with **(Evidence: …)** when grounded in page text.

```markdown
# Cloud-native review: PAGE_TITLE

**Source:** CONFLUENCE_URL_OR_PAGE_ID  
**Review focus:** Cloud-native architecture, dependencies, data, networking, operations.

## Summary

- Critical: N
- Major: N
- Minor: N
- Info: N
- Improvements: N
- Open questions: N

---

## Critical

### CRIT-001: SHORT_TITLE
Comment. If not fully evidenced, state what is missing.
(Evidence: "quote or section" — or "Not evidenced on page.")

## Major

### MAJ-001: SHORT_TITLE
...

## Minor

### MIN-001: ...

## Info

### INFO-001: ...

## Improvements

### IMP-001: ...

---

## Open questions

1. ...
2. ...

---

## HLD template coverage

| Section (HLD ch.) | Status (Present / Partial / Missing) | Notes |
|-------------------|--------------------------------------|-------|
| 1. Architecture Overview | ... | ... |
| ... | ... | ... |

_Or: "Not applicable: page is not an NSP HLD-style architecture document."_

---

## Review coverage checklist

Briefly state which dimensions were **in scope on the page** vs **not mentioned** (no fabrication). Mention whether **HLD template coverage** was evaluated.
```

Number findings sequentially **per severity** (CRIT-001, MAJ-001, …).

## Step 6 — Frequency hint

Prioritize comments on what the page **actually specifies** (diagrams, deployment, data flow). Use [reference.md](reference.md) to scan for **commonly forgotten** topics; only raise those as questions or info when the page is relevant but silent.

## Related

- Page fetch and URL parsing: [confluence-page](../confluence-page/SKILL.md)
- Authoring expectations (Confluence vs HLD sections): [create-repo-arch-doc](../create-repo-arch-doc/SKILL.md)
- Extended dimensions: [reference.md](reference.md)
