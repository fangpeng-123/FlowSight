# Interactive Graph Visualization Tech Survey (FlowSight)

**Goal:** Pick a renderer for an interactive Python-codebase knowledge graph — "floating, click-to-expand" overview, drill into modules for detail, potentially **thousands of nodes**. Must inform the web-app-vs-VS-Code-extension decision (ticket 08).

**Method note:** Live web fetching was network-blocked in this environment, so the figures below are synthesized from working knowledge of each library. Numbers marked *approx.* are rules of thumb; re-verify against each project's current docs/benchmarks before committing, especially for v5 rewrites (G6, Sigma v3, React Flow v12).

---

## Evaluation criteria

- **Scalability** — comfortable visible-node count before the UI lags (layout tick + render). More nodes are always *possible*; this is the "still feels good" threshold.
- **Layouts** — force-directed / hierarchical / dagre availability, and whether they run off the main thread (WebWorker) for big graphs.
- **Compound + expand/collapse** — native support for nested ("parent/child") nodes and collapsing them. *Core to FlowSight's "drill into modules" model.*
- **Interaction** — zoom / pan / hover / click out of the box.
- **License** — permissive vs copyleft / commercial.
- **Runtime** — plain browser? VS Code webview (Electron Chromium)?

---

## Per-library findings

### 1. D3.js (force-directed)
- **Rendering:** DIY — SVG (default), Canvas, or WebGL. `d3-force` is just physics; you draw.
- **Scalability:** SVG ~1–2k nodes; Canvas ~5–10k; `d3-force` uses Barnes-Hut quadtree so the *physics* is O(n log n), but DOM/render cost dominates.
- **Layouts:** `d3-force` (force-directed), `d3-hierarchy` (tree/tidy/cluster/pack/partition — hierarchical). No native dagre; `dagre` / `d3-dag` integrate cleanly.
- **Compound + expand/collapse:** None native. You build both.
- **Interaction:** DIY (`d3-zoom`, `d3-brush`, event listeners).
- **License:** ISC (BSD-equivalent, permissive).
- **Runtime:** Browser ✅ — VS Code webview ✅ (plain JS).
- **Verdict:** Maximum flexibility, maximum work. Great if you want a bespoke look and graphs stay small-medium. No batteries for the compound/expand model FlowSight needs.

### 2. Cytoscape.js
- **Rendering:** Canvas 2D; **WebGL renderer extension** (`cytoscape-webgl`) for large graphs.
- **Scalability:** ~5–10k nodes comfortable on canvas with perf hints (`wheelSensitivity`, `a11y` unlock, `batch`/`autoungrabify`); WebGL ext pushes higher. Mature, 12+ years, built for biological networks.
- **Layouts:** Built-in `cose` (force-directed), `breadthfirst` (hierarchical/BFS), `circle`, `grid`, `concentric`, `preset`. Extensions: **dagre**, klay/elk, cola, **fCoSE**, cose-bilkent, avsdf. One of the richest layout ecosystems.
- **Compound + expand/collapse:** **Compound nodes native** (parent/child, first-class). Expand/collapse via the well-maintained `cytoscape-expand-collapse` extension.
- **Interaction:** Native — zoom, pan, tap/click, hover (`mouseover`/`mouseout`), box selection, pinch-zoom.
- **License:** MIT.
- **Runtime:** Browser ✅ — VS Code webview ✅ (pure JS, no native deps).
- **Verdict:** Best all-rounder for "thousands of nodes + compound + expand/collapse" with the least assembly. The library AppMap builds on for code graphs (see below).

### 3. React Flow
- **Rendering:** DOM nodes (React components) + SVG edges. v11/v12.
- **Scalability:** Hundreds to low thousands. React reconciliation per node is the bottleneck; `onlyRenderVisibleElements` helps but is limited. ~1k+ gets janky.
- **Layouts:** None built-in — integrate `dagre` / `elkjs` / `d3-force` externally (dagre is the common pick).
- **Compound + expand/collapse:** **Compound ("parent") nodes supported** (`extent: 'parent'`, child nodes contained). Expand/collapse is DIY but a common, well-documented pattern.
- **Interaction:** Native — zoom/pan (built-in controls), click/hover via node/edge callbacks, selection, drag.
- **License:** MIT (v11). "React Flow Pro" adds paid collab features. Svelte Flow also MIT.
- **Runtime:** Browser ✅ — VS Code webview ✅ (React bundles fine into a webview).
- **Verdict:** Best DX and richest **per-node custom UI** (ideal for "drill into module for detail" panels) — but weakest raw scalability. Wins if you commit to aggressive expand/collapse so visible nodes stay < ~1–2k.

### 4. AntV G6 (v5)
- **Rendering:** Canvas (default), WebGL, SVG. v5 is a ground-up rewrite with a rendering abstraction.
- **Scalability:** Designed for large graphs; claims **~10k–50k+ nodes** with WebGL + WebWorker layouts. Strongest scalability story alongside Sigma.
- **Layouts:** Huge built-in set — `force`, `force2`, `fruchterman`, `gForce`, **`dagre`**, `radial`, `grid`, `circular`, `concentric`, `mds`, **`combo`** (combined force-directed), `compactBox`, `dendrogram` (tree), and more.
- **Compound + expand/collapse:** **Compound "combo" nodes native**, with built-in combo expand/collapse and tree collapse. First-class.
- **Interaction:** Built-in behavior system — zoom, pan, hover, click, drag, brush, context menu.
- **License:** MIT.
- **Runtime:** Browser ✅ — VS Code webview ✅.
- **Caveat:** Docs are predominantly **Chinese**; English docs exist but are sparser. API changed materially v4→v5; smaller Western community. 
- **Verdict:** Most feature-rich and best raw scalability, with the best *built-in* expand/collapse. Strong pick if the docs-language/community tradeoff is acceptable.

### 5. vis-network
- **Rendering:** Canvas.
- **Scalability:** A few thousand OK; Barnes-Hut physics helps, but it slows noticeably past ~2–5k with edges. Disable physics for static layouts.
- **Layouts:** Built-in physics (Barnes-Hut), **hierarchical layout** (DAG-ish, top-down/left-right), random, seeded.
- **Compound + expand/collapse:** **No native compound nodes.** "Clusters" exist but are a limited grouping concept, not true nesting. Expand/collapse is manual via cluster open/close API.
- **Interaction:** Native — zoom, pan, click, hover (tooltips), select, drag, multi-select.
- **License:** Dual MIT / Apache-2.0 (either).
- **Runtime:** Browser ✅ — VS Code webview ✅ (historically popular for VS Code extensions).
- **Caveat:** Maintenance has slowed (community fork territory). 
- **Verdict:** Easy to start, but **lacks real compound nodes** — poor fit for FlowSight's "drill into modules" model. Not recommended.

### 6. Sigma.js (v3) + Graphology
- **Rendering:** **WebGL** (custom shaders). Graphology is the data-model/graph-theory layer.
- **Scalability:** **10k–100k+ nodes** — Sigma's entire reason to exist. Best raw scalability here.
- **Layouts:** None built-in — `graphology-layout-forceatlas2` (WebWorker, very fast), `graphology-dagre`, `graphology-layout` (simple). 
- **Compound + expand/collapse:** **No native compound nodes.** Graphology doesn't model nesting natively — DIY via attributes. Expand/collapse is DIY.
- **Interaction:** Via `@sigma/` plugins (mouse-events, hover, etc.) — zoom/pan/hover/click available but assembled.
- **License:** MIT (Sigma and Graphology).
- **Runtime:** Browser ✅ — VS Code webview ✅ *if WebGL is available in the webview* (desktop Electron = yes; risky for any headless/remote/CI rendering).
- **Verdict:** Best raw scalability, but **no compound nodes** and more assembly work. Only worth it if a *single view* routinely shows >10k visible nodes — which contradicts FlowSight's expand/collapse-into-detail model.

### 7. Code-graph-specific renderers (AppMap / CodeSee et al.)
- **AppMap:** Its interactive dependency/trace diagrams are built in `appmap-js` on top of a **graph library** — historically **Cytoscape.js** for the dependency-graph view (verify on the current repo). License: MIT (`appmap-js`). Validates Cytoscape for exactly FlowSight's use case.
- **CodeSee:** Built a **custom React-based renderer** (force-directed over its own layout) for its "Code Maps." The **company shut down in 2023**, so it is not a maintained, reusable dependency. Lesson: custom renderers are a maintenance liability; lean on a maintained graph lib.
- **Other code-graph tooling** (mostly *non-interactive*, for contrast): `madge`/`dependency-cruier` → DOT/Graphviz → static SVG via `viz.js`; webpack-bundle analyzers → static treemaps. Visual Studio "Code Map" is closed/internal. None give FlowSight's interactive expand model.
- **Takeaway:** The maintained code-graph tools (AppMap) standardized on **Cytoscape**; the custom one (CodeSee) died. This is a strong signal.

---

## Comparison matrix

| Library | Comfortable nodes | Compound nodes | Expand/collapse | Best layouts | License | Browser | VS Code webview |
|---|---|---|---|---|---|---|---|
| D3.js | ~1–10k (render-dependent) | ✗ DIY | ✗ DIY | force, hierarchy, +dagre | ISC | ✅ | ✅ |
| **Cytoscape.js** | ~5–10k (WebGL ext higher) | **✅ native** | ✅ ext (`expand-collapse`) | cose, **dagre**, fCoSE, cola | MIT | ✅ | ✅ |
| React Flow | ~hundreds–low thousands | ✅ parent | ✅ DIY (common) | dagre/elk (external) | MIT | ✅ | ✅ |
| **AntV G6 v5** | **~10k–50k+** | **✅ combo** | **✅ built-in** | force, **dagre**, combo, radial, tree | MIT | ✅ | ✅ |
| vis-network | ~2–5k | ✗ (clusters only) | ✗ manual | Barnes-Hut, hierarchical | MIT/Apache | ✅ | ✅ |
| Sigma.js+Graphology | **~10k–100k+** | ✗ DIY | ✗ DIY | ForceAtlas2, dagre (external) | MIT | ✅ | ⚠️ needs WebGL |
| AppMap's stack | (uses Cytoscape) | via Cytoscape | via Cytoscape | — | MIT | ✅ | ✅ |
| CodeSee | custom | — | — | custom | defunct (2023) | ✅ | n/a |

---

## Recommendation

**Top pick: Cytoscape.js** as the primary interactive graph layer.

- Native **compound nodes** + the `cytoscape-expand-collapse` extension map directly onto FlowSight's "click-to-expand / drill into modules" model with the least custom code.
- Comfortable with **thousands of nodes**; the WebGL renderer extension covers growth beyond ~10k if needed.
- **MIT**, pure JS, **no native dependencies** → drops cleanly into *both* a web app and a VS Code webview. AppMap validates it for code graphs; CodeSee's custom path died.
- Mature layout ecosystem (fCoSE for stable, readable code-graph layout; dagre when a hierarchical/DAG view is wanted).

**Strong alternative: AntV G6 v5** if you routinely expect **>10k visible nodes in one view** or want the richest *built-in* combo/expand/layout set. Tradeoff: docs are Chinese-primary and the v5 API is still settling — higher learning/risk curve for a solo tool.

**Secondary, for detail panels only: React Flow.** If "drill into a module" should show a rich, bespoke per-node UI (code, symbols, metrics), React Flow's custom-node DX is unmatched. Consider it for an expanded-module *detail view*, not the whole-codebase overview — or as the whole UI *only if* you commit to aggressive expand/collapse keeping visible nodes < ~1–2k.

**Avoid for FlowSight:** Sigma.js (no compound nodes — fights the drill-in model; only wins if single views exceed ~10k nodes, which expand/collapse should prevent) and vis-network (no real compound nodes, slowing maintenance).

### What this implies for the web-app-vs-VS-Code-extension decision (ticket 08)

1. **The renderer does not force the deployment choice.** Cytoscape, G6, and React Flow are all pure JS/TS that run identically in a browser tab and in a VS Code webview (Electron Chromium). Picking Cytoscape keeps **both doors open** with one rendering codebase.
2. **Recommended architecture:** build the graph layer as a **framework-agnostic JS module** (Cytoscape core + layout/expand-collapse extensions + your data adapter). Wrap it twice: once in the web app (any framework) and once in a VS Code webview that loads the same bundle and receives graph data via the extension API / `postMessage`. One renderer, two hosts.
3. **WebGL-based picks (Sigma, and to a lesser degree G6's WebGL mode) slightly favor the web-app path** — WebGL works in desktop Electron webviews but is riskier for any headless/remote/CI scenario. Cytoscape's Canvas-first default sidesteps this entirely, which is another point for it as the default.
4. **React Flow couples the renderer to React** — fine for both web app and webview (both run React), but a heavier bundle in the webview and a firmer framework commitment. Acceptable, just less neutral than Cytoscape.
5. **Net guidance for ticket 08:** choose Cytoscape now; **decide web-vs-extension on product grounds** (reach / iteration speed / sharing → web app; deep editor integration, auto source-of-truth from the workspace, zero-install for the user → extension) rather than on renderer constraints. A shared Cytoscape core means you can ship one first and add the other later without rewriting the graph layer.
