# agentic-workspace docs

Documentation for agentic-workspace tooling.

## Arch doc convention — per-repo `docs/` layout

Architecture documents (HLD, Confluence body, draw.io diagrams) live under each **target repo's own `docs/`** directory — not in agentic-workspace. Standard layout:

```
<repo>/docs/
  confluence/
    body.html                            # Confluence page body (HTML)
    diagrams/                            # draw.io files for Confluence upload
      <repo>_components_v1.drawio
      <repo>_data_flow_v1.drawio
  actual/                                # Detailed local HDD (markdown)
    System_Design_HighLevel.md
```

| Repo | Confluence body | Local HDD | Diagrams |
|------|----------------|-----------|----------|
| **device-registry** | `docs/confluence/body.html` | `docs/actual/System_Design_HighLevel.md` | `docs/confluence/diagrams/` |
| **comm-layer-server** | `docs/confluence/body.html` | — | `docs/confluence/diagrams/` |
| **comm-subscription-server** | — | [docs/PLAN.md](../../comm-subscription-server/docs/PLAN.md) | [docs/diagrams/](../../comm-subscription-server/docs/diagrams/README.md) |

To create an arch doc for a new repo, use the **create-repo-arch-doc** skill and generate files directly under `<repo>/docs/confluence/` and `<repo>/docs/actual/`.
