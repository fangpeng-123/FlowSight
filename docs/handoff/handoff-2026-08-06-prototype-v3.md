# FlowSight — Handoff · 2026-08-06

> Continues the `/wayfinder` effort for **FlowSight**. Read the canonical map first:
> `.scratch/flowsight/map.md`. This doc orients a fresh agent; it does not re-derive decisions
> already captured in the map, issues, or research notes — those are referenced by path.

## What FlowSight is

A **personal** Python-codebase tool that builds an interactive knowledge graph — files, functions,
data-flow, interface contracts, dependency direction, risk hotspots — by **leveraging LLM capability
for structural querying and graph construction**, with a **static skeleton overlaid by runtime
data-flow traces**, visualized as a **floating, click-to-expand graph** (clean overview, drill into
modules for detail).

Standing shape (from destination grilling, recorded in `map.md`):
- Personal tool, self-use, runs on the user's machine. Not a product.
- Python-only; vision is to support *any* Python project (the ASR→LLM→TTS voice-agent example is
  illustrative, not a v1 scope limit).
- LLM-centric (model does structural querying + graph drawing, not a pure deterministic parser).
- Hybrid: static graph skeleton + runtime data-flow overlay.
- Visual-first: **the user has reading difficulty (阅读障碍)** — graphs + IDE search beat
  line-by-line reading. Keep the main view clean; expand modules on demand.
- The **four content areas are the core deliverable and must be prominent**: (1) core data
  structures — key entities & relations; (2) interface contracts — I/O, error codes, boundary
  conventions; (3) dependency graph — call direction & data flow; (4) risk list — pitfalls & avoidance.

## How we're working: `/wayfinder`

Charted a decision map. Mechanics (from `map.md`):
- Map = `.scratch/flowsight/map.md` (Destination, Decisions-so-far, Not-yet-specified, Out-of-scope).
- Tickets = `.scratch/flowsight/issues/NN-<slug>.md`. Research findings = `.scratch/flowsight/research/<name>.md`.
- One HITL ticket per session (research is the exception). Claim = `Status: claimed`; resolve =
  append `## Answer` + `Status: resolved` + add a Decisions-so-far line to `map.md`.

The map is "done" (build-ready) when: core architecture, graph schema & views, runtime overlay
technique, visualization IA + tech, and medium are all decided.

## Ticket status

| # | Ticket | Status | Note |
|---|---|---|---|
| 01 | landscape-research | **research DONE, NOT formally resolved** | `research/landscape.md` was written (full prior-art survey: CodeGraph, AppMap, CodeSee, Sourcegraph/Cody, Swimm, jedi, pyright, tree-sitter, Semgrep, Sourcetrail, bloop). But `issues/01` still says `Status: claimed` and `map.md` has no 01 decision line. **Closing 01 is a quick task:** read `landscape.md`, extract the reuse-vs-build list, append `## Answer` to `issues/01`, mark resolved, add a Decisions-so-far line to `map.md`. |
| 02 | python-primitives-research | resolved | Skeleton: `ast`+`importlib`+`jedi` (pyright optional). Overlay: `viztracer`+`sys.monitoring`+`sys.audit`+`py-spy`/`scalene`+targeted monkey-patch. Only viztracer fixes async chains; only py-spy/scalene see C frames. |
| 03 | graph-viz-research | resolved | **Cytoscape.js** (compound + expand-collapse, MIT, browser & VS Code webview). G6 v5 alt for >10k nodes; React Flow for detail panels. Renderer is deployment-neutral. |
| 04 | core-architecture | resolved | Parser skeleton (`ast`+`jedi`, exact/free/scales) + LLM enrichment (eager module summaries + lazy deep per-function on drill-down), cached per code-hash. Skeleton trusted, annotations advisory. Runtime overlay = actual(viztracer)-on-expected(LLM). |
| 05 | graph-schema-views | resolved | Nodes Module/Function/Class/External/**DomainEntity**(LLM). Edges calls/imports/contains/references/produces/consumes/transforms/data_flow. Attrs tagged parser(trusted)/LLM(advisory)/runtime(actual). 4 views = data subsets. |
| 06 | runtime-overlay-technique | **PENDING, unblocked** (grilling) | Not worked. How a captured `viztracer` trace maps onto the parser skeleton — the "actual-on-expected" overlay mechanics. Unblocks the runtime half of the vision. |
| 07 | visualization-ia | **IN PROGRESS** (prototype) | v3 just built — **awaiting user reaction**. See next section. |
| 08 | medium-shell | **PENDING, unblocked** (grilling) | Not worked. Local web app vs VS Code extension. Decide on product grounds (renderer is neutral per 03). Last decision before MVP build. |

## Immediate next action — resolve 07 (visualization prototype)

Prototype lives at `.scratch/flowsight/prototype/index.html` (single self-contained HTML + Cytoscape.js
from CDN; no build step; open in browser). Iteration history:

- **v1** — compound containers. REJECTED: "和我想的差别很大，我想要的是 obsidian 的那种知识图谱…"
- **v2** — Obsidian-style tree-expand. REJECTED: "感觉很浅很粗糙…背景纯黑的，而且并没有明显标注[四个内容]"
- **v3** — **JUST BUILT, awaiting reaction.** Design:
  - Pure-black canvas, floating force-directed graph (`cose` layout), small flat circles,
    3-tier size/color hierarchy: modules=teal (large), functions=blue (small), data entities=orange
    (round-rectangle); functions carrying a risk get a **red ring**. Minimal small labels.
  - Thin edges: calls (gray, arrowed), contains (dark, no arrow), data-flow produces/consumes
    (orange, dashed, arrowed).
  - Click a module → expand/collapse its children (Obsidian-style). Click any node → highlight its
    neighborhood, dim the rest, and the right panel drills into that node's four-area detail.
  - **Right side panel (persistent)** holds the four content areas — 依赖关系 / 核心数据结构 /
    接口契约 / 风险清单 — so the graph stays clean while all four stay prominent. Default shows
    project-level overview; selecting a node drills the panel to that node's contracts/deps/entities/risks.
  - **Top dimension tabs** (依赖/数据结构/契约/风险) highlight one dimension across the whole graph
    and scroll the panel to that section — makes any single dimension fully prominent on demand.

- **Reference image** the user wants matched: `C:\Users\Administrator\Downloads\downloaded-image.jpeg`
  — pure-black background, Obsidian-style floating small circles, thin lines. ⚠️ The user explicitly
  said "背景纯黑的" even though the image may read as light — **trust the user: use pure black (#000).**
- The user **approved the v3 direction in principle** before it was built: the four areas don't have
  to live on the floating nodes — "可以单开一个侧边展示栏，这样不会显得拥挤…你尝试给出方案，我审核最终确认".
  So v3 implements: clean graph + right panel + dimension tabs.

**On the user's reaction to v3:**
- If approved → append `## Answer` to `issues/07`, `Status: resolved`, add a Decisions-so-far line to
  `map.md` (visualization IA = black floating graph + persistent right four-area panel + dimension
  highlight tabs; renderer Cytoscape.js from 03).
- If it needs changes → iterate `prototype/index.html` directly (single file, no build). Re-run the
  vision skill on the reference image if you need to re-check the aesthetic.

## Then — remaining tickets (in suggested order)

1. **Close 01** (quick — research already done; just formalize).
2. **06 runtime overlay technique** (grilling): viztracer-trace ↔ parser-skeleton mapping; how
   actual-on-expected is computed and rendered. Use `/grilling`.
3. **08 medium shell** (grilling): local web app vs VS Code extension. Use `/grilling`. This is the
   final decision — once 06/07/08 + 01-close are done, the map is build-ready and MVP implementation
   can start.

## Standing constraints (from global `CLAUDE.md` — must follow)

- **Git push to GitHub MUST go through the V2Ray HTTP proxy `http://127.0.0.1:10808`** (git is
  globally configured `http.proxy`/`https.proxy`). Before `git push`, confirm V2Ray is running. If
  you see `Recv failure: Connection was reset` or `Failed to connect to github.com port 443`, V2Ray
  isn't running — remind the user to start it, and verify `git config --global http.proxy` is still
  `http://127.0.0.1:10808` (re-set if dropped). **`gh` CLI succeeding ≠ `git push` succeeding** —
  don't infer git is fine from a gh success.
- **No native image reading** (the session model, e.g. glm-5.2, has no vision; `Read` can't see image
  content). For any image (reference image, screenshots), use the vision skill script:
  `node "C:/Users/Administrator/.claude/skills/vision/vision.js" "<path>" "<question in Chinese>"`
  (second arg optional; config in the script's sibling `.env`, overridable by env vars). For a URL,
  pass `--url "<url>"`.
- **CodeGraph**: if a `.codegraph/` directory exists at the repo root, reach for CodeGraph (MCP tools
  `codegraph_explore`/`codegraph_node`, or shell `codegraph explore`/`codegraph node`) BEFORE
  grep/find/read. FlowSight does **not** currently have one — skip CodeGraph unless the user indexes.

## User profile & preferences (carry forward)

- Reading difficulty (阅读障碍) → visual-first; show prototypes and let them react; don't over-describe
  in prose. Keep the main view clean; expand for detail on demand.
- Personal tool, self-use, Python-only, vision = any Python project.
- LLM-centric structural querying.
- Aesthetic: pure-black background, Obsidian-style floating force-directed graph.
- The four content areas must be prominently displayed — this was the explicit complaint about v2.

## Suggested skills (invoke these)

- **`/wayfinder`** — continue the map/ticket workflow; pick the next ticket, work it HITL.
- **`vision` skill** — for reading any image (reference image, user/prototype screenshots). Script:
  `node "C:/Users/Administrator/.claude/skills/vision/vision.js" "<path>" "<question>"`.
- Per `map.md` Notes, every decision session should consult: **`/grilling`** + **`/domain-modeling`**
  (for decisions), **`/prototype`** (for look-and-feel), **`/research`** (for outside-codebase facts).
  Tickets 06 and 08 are grilling tickets → lead with `/grilling`.

## Key artifact paths

- Map (canonical tracker): `.scratch/flowsight/map.md`
- Issues: `.scratch/flowsight/issues/01..08-*.md`
- Research: `.scratch/flowsight/research/{python-primitives,graph-viz,landscape}.md`
- Prototype (current = v3): `.scratch/flowsight/prototype/index.html`
- Reference image (target aesthetic): `C:\Users\Administrator\Downloads\downloaded-image.jpeg`
- Full prior transcript (if detail needed): `C:\Users\Administrator\.claude\projects\F--FlowSight\f2ed3824-7f46-4e4a-a012-0f969e294671.jsonl`
