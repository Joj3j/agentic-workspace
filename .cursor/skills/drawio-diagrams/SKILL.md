---
name: drawio-diagrams
description: Draw.io diagram authoring guide — layout (horizontal vs vertical vs hybrid), flow clarity, edge/label non-overlap, swimlanes, UML sequence diagrams ("sequential diagram" = lifelines + messages), colors/styles, and version workflow. Use when creating or editing .drawio / .drawio.svg files, files under docs/**/diagrams/**, architecture or sequence/data-flow diagrams, or when the user asks to draw, lay out, or restyle a draw.io diagram.
---

# Draw.io Diagram Drawing Guide

## Basic specifications

### File naming

- **Format:** `[ModuleName]_[ScenarioDescription]_[VersionNumber].drawio`
- **Example:** `ai_assistant_architecture_v1.drawio`

### Component colors and styles

- **Diagram background:** Use a light canvas background (e.g. white `#ffffff` or very light gray) so connector lines and text remain visible; avoid black or dark background unless using light-colored lines and light font.
- **Border line width:** 2 (`strokewidth=2`) for all components.
- **Text/font:** Use dark font on light fills so labels are readable. Set `fontColor=#1a1a1a` (or `#333333`) for body text; use the same or a matching dark shade for each category below. Never use white text on light fills.

| Category | Fill | Border | Font color |
|----------|------|--------|------------|
| **ALL/LLM** | `#ddaedf` (light mauve) | `#6c8e9f` | `#2d1b4e` |
| **AT Service / Data** | `#ffffcc` (light yellow) | `#d6b655` | `#5c4a1a` |
| **System services** | `#e8eef4` (light blue-gray) | `#606666` | `#1a1a1a` |
| **Clients / callers** | `#e3f2fd` (light blue) | `#1976d2` | `#0d47a1` |
| **User / External** | `#fff8e1` (light cream) | `#000000` | `#1a1a1a` |

- **Other:** Use two-color solid lines; prefer rounded rectangles; keep `strokewidth=2`. Edge labels: `fontColor=#333333` for readability.

### Component state and style

- **Standard component:** Rounded rectangle with border.
- **Non-standard component:** Large rounded rectangle, light background.
- **Dashed box:** Use for real connections; avoid dashed-line intersections.
- **Experience:** Put descriptions in the diagram; emphasize key information in bold.

## Drawing rules

### Layout direction: choose horizontal, vertical, or hybrid

Pick the primary reading direction from what the diagram is **about**—not a single global rule.

| Pattern | Prefer | Typical use |
|--------|--------|-------------|
| **Horizontal (LR)** | Main flow **left → right** | Request/response pipelines, same-abstraction peers (e.g. Client → API → Service → Store), sequence of stages with one dominant direction. |
| **Vertical (TB)** | Main flow **top → bottom** | **Tiered** systems (**NBI → core → SBI**), dependency stacks, swimlanes by trust zone or network boundary, “northbound / southbound” telco-style views, “data descends / results return” stories. |
| **Hybrid** | **Bands vertical**, detail **horizontal** inside a band | Large swimlanes (e.g. one lane per subsystem); inside each lane, arrange components LR if they are peers. Cross-band connectors are then mostly **vertical** with short horizontal elbows. |

**Rules of thumb**

1. **One primary direction per diagram:** Do not mix unrelated TB and LR main flows without swimlanes or grouping—readers should know whether to scan **across** or **down** first.
2. **Swimlanes:** When boundaries matter (client vs server pod vs external), use **horizontal swimlanes** stacked **vertically** (NBI on top, system in the middle, external/SBI below). Match **industry vocabulary** (e.g. NBI/SBI) to **canvas order** (top = north).
3. **Peer components** inside one lane: lay them **horizontally** with even spacing so fan-out/fan-in edges can use **different exit/entry ports** (see edges below).
4. **Gaps between bands:** Leave **clear vertical whitespace** between major blocks (e.g. 40–90px between swimlane bottoms and the next lane top) so **crossing edges and labels** are not squeezed against boundaries.

**Legacy AI-service template:** For the **AI service architecture** flow (Client → Service Layer → AT → LLM), keep **left-to-right** layering as in [Standard architecture diagram board](#standard-architecture-diagram-board). That template does **not** override tiered comm/NBI-SBI diagrams—use **vertical** stacking there.

### Terminology: "sequential" diagram

When a doc or request says **sequential diagram**, **sequence flow**, or **sequential flow** (in the sense of *who talks to whom over time*), use a **UML sequence diagram** — **not** a horizontal pipeline of numbered rounded rectangles.

- **Use:** [Sequence diagram (UML)](#sequence-diagram-uml) — lifelines (`shape=umlLifeline`), time **top → bottom**, `elbowEdgeStyle` messages, self-calls with curved loops, dashed edges for returns/async streams where appropriate.
- **Reference examples:** `newarch/apps/int/nsp-device/device-registry/docs/diagrams/device_registry_data_flow_v1.drawio`, `comm-layer-server/docs/design/diagrams/comm_layer_server_async_ticket_lifecycle_sequential_v1.drawio` (sibling repo).
- **Naming:** Filenames may include `sequential` or `sequence` (e.g. `*_sequential_v1.drawio`, `*_direct_grpc_sequence_v1.drawio`); content must still follow the UML sequence pattern above.

**Example (hybrid TB + LR):** `comm-layer-server/docs/design/diagrams/comm_layer_server_async_config_nbi_sbi_v1.drawio` — swimlanes stacked **top → bottom** (NBI / CLS / SBI), peers **left → right** inside SBI, **comm-operator** routing inside CLS, **solid** config path vs **dashed** deployment notifications on **separate** `exitX` from Data Deployer, **FIFO** policy in a dashed note + edge labels.

### Flow clarity (so the story is obvious)

- **Title / caption:** One line at the top for **scope** (what system, what scenario); optional **caption** at the bottom for **policies** (FIFO, limits, parallelism) that do not fit on edges.
- **Swimlane titles:** Short, consistent (**NBI**, **COMMUNICATION LAYER SERVER**, **SBI**); **UPPERCASE** or **bold** for the main system lane.
- **Edge labels:** Prefer **verbs or protocol artifacts** (`async RPCs`, `Set / BatchSet`, `open stream`, `enqueue FIFO`) over vague arrows. For dense diagrams use **small font** (`fontSize=8`) but keep **`labelBackgroundColor`** so labels stay readable on crossings.
- **Policy notes:** Long rules (e.g. bulk size, FIFO drain) belong in a **dashed note** or **text box** beside the owning component—not on every edge.
- **Return / async paths:** Use **dashed** edges and a **visually separate** route (e.g. different `exitX`/`entryX` or vertical offset) from the primary solid request path so **two flows do not share the same corridor**.
- **Alignment:** Grid-align shapes; keep **one column** for a vertical spine (e.g. dispatcher → routing) when possible.

### Layer usage and consistency

- Separate **data-flow** from **control/API** concerns when the diagram would otherwise be cluttered—either **two diagrams** or **grouping** + clear labels.
- Keep **stroke width**, **font family/size hierarchy**, and **edge color** consistent across one file (`strokeColor=#2c5282` for primary edges on light canvas unless a legend says otherwise).

## Standard architecture diagram board

### AI service architecture flow

- `[Client] → [Service Layer] → [AT Service] → [AT Decision Layer] → [LLM Layer]`
- User Interface → Business Service → AT Interface → LLM Service
- New Data → Agent → Knowledge Base

### Containers and components

- **Logical grouping:** When several boxes are components of one logical block (e.g. "Device Registry", "Service Layer"), place them inside a **single container** — one large rectangle or square with a clear label (e.g. "Device Registry"). Put the component boxes as **children** of that container so they appear inside the big rectangle; do not leave them as separate floating blocks in the center.
- **Application/container name:** Make the main application or container name **centralized and noticeable**: use **UPPERCASE** (e.g. "DEVICE REGISTRY"), **center** the title (`align=center`), use **bold** (`fontStyle=1`) and a slightly **larger font** (`fontSize=14` or `16`) so it stands out as the diagram title for that block.
- **Module container:** Width 550px, height 270px (or enough to fit inner components), light gray outer border; fill per category (e.g. system services fill/border).
- **Component container:** Width 120px, height 80px, slightly rounded corners.
- **Border line width:** `strokewidth=2`; use orthogonal style.
- **Text:** Left-aligned; centered title and subtitle; use dark `fontColor` per category table above (e.g. `#1a1a1a`) so text is readable on light fills.

### Flow line specifications

- **Connector visibility:** Lines must always contrast with the diagram background. **Do not use black (#000000) for connector stroke** on a dark background. Use a visible stroke color: e.g. `strokeColor=#2c5282` (dark blue) or `#1a365d` (navy) on light canvas; on dark canvas use a light stroke (e.g. `#90cdf4` or `#e2e8f0`).
- **Edge label boxes:** For connector labels (e.g. "sync", "upload schemas", "SubscribeNotifications"), the **label background must be light** so text is readable. Set `fillColor=#ffffff` and `labelBackgroundColor=#ffffff` (or light cream `#fff8e1`); set `fontColor=#1a1a1a` (dark) for the label text. Never use a dark label background with dark text.
- **Edge labels and internal lines in foreground:** Edge labels and connectors between components must sit **in front of** swimlane fills. In XML, under the same parent, list **all vertex (shape) cells first, then all edge cells** so edges and labels draw on top.
- **Main flow line:** Solid line with arrowhead; `strokeWidth=2` (or `strokewidth=2` in style string); use the visible stroke color above. Prefer `edgeStyle=orthogonalEdgeStyle` for architecture diagrams unless a curved style is intentional.
- **Auxiliary flow line:** Dashed line with arrowhead; `strokeWidth=2`, `dashed=1`, `dashPattern=6 6`; same stroke color as primary unless a legend says otherwise.

#### Arrows and text must not overlap shapes or each other

1. **Connection ports (preferred over default center):** For **fan-out** from one box to several, set **different** `exitX` / `exitY` on the source (e.g. `0.2` vs `0.8` on the bottom edge) and **different** `entryX` on targets (e.g. `0.25` vs `0.75`) so **orthogonal** routes **split early** and do not run **through** sibling boxes. For **fan-in**, mirror with target `entryX` / `entryY`.
2. **Do not route through unrelated shapes:** If the router draws an edge **across** another rectangle, add **`Array as="points"`** waypoints for orthogonal elbows **around** the obstacle, or move the shape / use side ports (`exitX=0` or `exitX=1`).
3. **Separate solid vs dashed corridors:** **Dashed** paths (notifications, returns, side channels) should use **different horizontal or vertical channels** than the **solid** main path—e.g. **different** `exitX` on the source so dashed and solid edges **do not share a long colinear segment**.
4. **Labels vs lines and shapes:** If a label overlaps **another** edge or **passes through** a box, shorten the label and move detail to a **note**; add **waypoints**; or use smaller `fontSize` (e.g. `8`) while keeping **`labelBackgroundColor=#ffffff`**. Optionally adjust draw.io **label position** on the edge.
5. **Parallel edges:** Two edges between the **same** pair of nodes should **not** reuse identical geometry—offset with waypoints or different ports.
6. **Crossing swimlane boundaries:** Edges crossing lanes need **enough vertical gap** between swimlanes; if labels crowd the boundary, **increase** spacing or place labels only on **short** segments.
7. **Line end spacing:** Keep **≥ 20px** visual clearance where multiple lines meet one shape; avoid **three or more** edges meeting the **same** corner—distribute connections around the perimeter.
8. **Fan-out below, not above the box row:** When a component fans out to multiple peer boxes in the same horizontal row, route edges **below** the row through a corridor between rows — **never above** the first row. Above-row routing overlaps container/swimlane title text (`verticalAlign=top`). Exit the source from its **bottom** edge (`exitY=1`) with **staggered `exitX`** values per target, route horizontally through the corridor at **staggered y-values** (≥ 7px apart), then enter each target from its **bottom** (`entryY=1`) or side. Leave **≥ 50px** vertical gap between the bottom of the top row and the top of the next row to fit the corridor; if the gap is too tight, push the second row down.

**Checklist before saving**

- [ ] Primary flow direction (LR vs TB) matches diagram type; swimlanes ordered logically (e.g. NBI above SBI).
- [ ] No edge runs **through** an unrelated box; waypoints or ports adjusted if needed.
- [ ] Solid and dashed **long** segments do not **coincide**; fan-out/fan-in uses **split** ports.
- [ ] Edge labels readable (**light label background**); none hidden by **another** line or **shape** text.
- [ ] Fan-out edges route **below** the box row (not above where container titles sit); corridor has ≥ 50px vertical gap.
- [ ] Vertices listed **before** edges in XML for the same parent.

---

## Sequence diagram (UML)

Use this pattern for **data flow** or **interaction** sequence diagrams (e.g. Ch 7 HLD). This is also the required pattern when the ask is for a **sequential diagram** / **sequence flow** — see [Terminology: "sequential" diagram](#terminology-sequential-diagram). Same file-naming and version workflow as above; styling below is specific to sequence diagrams.

### Shape and structure

- **Participants (lifelines):** Use draw.io UML lifeline shape: `shape=umlLifeline`, `perimeter=lifelinePerimeter`, `container=1`, `dropTarget=0`, `collapsible=0`, `recursiveResize=0`, `outlineConnect=0`, `portConstraint=eastwest`.
- **Lifeline style:** `newEdgeStyle={"edgeStyle":"elbowEdgeStyle","elbow":"vertical","curved":0,"rounded":0}` so messages use vertical elbow routing.
- **Vertical lifeline line (dotted bar):** Make the vertical bar **thick and visible**: set `strokeWidth=4` (or 3–4) and a bright `strokeColor=#2c5282` on the lifeline shape so the bar contrasts with the background.
- **Layout:** One lifeline per participant; left-to-right order by **request flow** (e.g. if the first request is Service → External, place External to the right of Service). Time flows **top to bottom**; space message rows evenly (e.g. ~30px vertical gap for compact diagrams).
- **Lifeline size:** Width ~100px (compact) or ~150px; height sufficient for all messages (e.g. 460–620px). Align all lifelines to the same top y and same height. For consistency with component diagrams, use the same page size (e.g. `pageWidth=1600`, `pageHeight=1200`) and keep content in positive coordinates.

### Sequence diagram colors (yellow/green/gray theme)

| Role | Fill | Stroke (lifeline + vertical bar) | Font |
|------|------|----------------------------------|------|
| **Callers / external (e.g. Device Admin, Discovery Service, Clients)** | `#ffe6cc` (light orange) or `#fff9c4` (light yellow) | `#2c5282` (bright blue; use for vertical bar visibility) | `#000000` (black for readability) |
| **Service (e.g. Device Registry)** | `#d5e8d4` (light green) | `#2c5282` | `#000000` |
| **Storage / external system (e.g. etcd, Schema Server)** | `#e8f4e8` (light green) or `#f5f5f5` (light gray) | `#2c5282` | `#000000` |

Use **black font** (`fontColor=#000000`) on light fills so participant names are clearly visible. For **message (edge) labels**, set `fillColor=#ffffff`, `labelBackgroundColor=#ffffff`, and `fontColor=#000000` so labels do not disappear on dark strokes.

### Messages (edges between lifelines)

- **Style:** `edgeStyle=elbowEdgeStyle`, `elbow=vertical`, `curved=0`, `rounded=0`, `endArrow=block`, `strokeColor=#2c5282`, `strokeWidth=2`. No arrow on the return leg if you show a reply.
- **Label:** Put the message name on the edge (`value="..."` on the edge cell). Use `verticalAlign=bottom` (or `middle`). Set `fillColor=#ffffff`, `labelBackgroundColor=#ffffff`, `fontColor=#000000` so the label is visible.
- **Self-calls (same participant):** Edge from lifeline to itself; use `curved=1` and two points to form a small loop so the message (e.g. "Notify subscribers") is readable. Example: `source` and `target` same id; `Array as="points"` with two points offset vertically.
- **Initial/startup flow:** Place at the top of the sequence (first message row). Set the message waypoint **y** low enough (e.g. y ≥ 90) so the horizontal segment runs **below** participant header boxes and does not overlap middle components (e.g. etcd).

### Order of elements in XML

- List **lifeline (vertex) cells first**, then **message (edge) cells**, so message arrows and labels draw on top and remain visible (same as for flow diagrams).

### Summary

- **Lifelines:** `umlLifeline`, `strokeWidth=4` and `strokeColor=#2c5282` for a thick, visible vertical bar; black text (`#000000`); yellow/orange for callers, green for service, light green/gray for storage/external.
- **Participant order:** Left-to-right by request flow (e.g. Discovery_Service, Device_Registry, Device_Admin, etcd, Clients, Schema_Server) so arrows match direction.
- **Messages:** Elbow vertical, block arrow, bright stroke `#2c5282`; edge labels with white background and black text; self-calls curved with two points.
- **Initial flow:** At top; waypoint y low enough to avoid overlapping middle components.
- **File:** Same naming `[Module]_data_flow_v1.drawio`; version workflow and CHANGELOG as in Version management.

---

## Version management

### File naming (versioned)

- **Format:** `[ModuleName]_[ScenarioDescription]_v[VersionNumber]_[Date].drawio`
- **Example:** `alconf_system_flow_v1.1_20250619.drawio`

### Version meaning

- **v1.0:** Initial version.
- **v1.1:** Minor changes (component adjustment, style change).
- **v2.0:** Major changes (structure change, module refactor).

### Standard workflow

1. **Copy to create backup**
   ```bash
   cp [original_filename].drawio [original_filename]_v[version]_[date].drawio
   ```
   Example: `cp alconf_system_flow_v1.0_20250619.drawio alconf_system_flow_v1.1_20250619.drawio`

2. **Modify on the backup:** Make all edits in the backup file, not the main file.

3. **Submit and CR:** Check requirements; ensure diagram opens and edits normally; confirm changes match expectations.

4. **Replace main file**
   ```bash
   cp [backup_filename].drawio [main_filename].drawio
   ```

5. **Update CHANGELOG.md:** Record the version change (see format below).

### CHANGELOG format

- **Version line:** `v[Version] - [Date]` (e.g. `v1.1 - 2025-06-19`).
- **Added:** New files (edit and upload new file).
- **Fixed:** With short problem description.
- **Technical improvement:** With short change description.

### Best practices

- **Frequent backups:** Prefer modifying copies; avoid editing the single "main" file directly.
- **Regression confirmation:** After changes, verify the diagram still meets all requirements.
- **Timely recording:** Update CHANGELOG promptly so important changes are not lost.
- **Keep history:** Do not delete old versions; keep backups of previous diagrams.
