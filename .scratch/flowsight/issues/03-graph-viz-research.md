# 03 - Graph visualization tech

Type: research · Status: resolved · Blocked by: -

## Question

Which interactive graph-visualization tech fits a "floating, click-to-expand, clean overview with drill-down" codebase graph (potentially thousands of nodes)?

Cover: D3 force-directed, Cytoscape.js, React Flow, AntV G6, vis-network, Sigma.js/WebGL, and code-graph-specific renderers. For each: scalability (node count), layout algorithms, expand/collapse support, interaction model, license, and whether it runs in a browser and/or a VS Code webview. Goal: inform the visualization architecture (ticket 07) and the web-vs-extension medium (ticket 08).

## Answer

Findings: `../research/graph-viz.md` (128 lines; figures synthesized from working knowledge - web was blocked, re-verify against current docs/benchmarks before committing, especially v5 rewrites.)

**Top pick: Cytoscape.js** - native compound nodes + the `cytoscape-expand-collapse` extension map directly onto "click-to-expand / drill into modules"; ~5-10k comfortable nodes (WebGL ext pushes higher); MIT, pure JS, no native deps → runs in both a browser tab and a VS Code webview. AppMap validates Cytoscape for code graphs; CodeSee's custom renderer died (maintenance-liability lesson).

**Alternative:** AntV G6 v5 (>10k nodes, richest built-in combo/expand/layout set; tradeoff: Chinese-primary docs, v5 API still settling).
**Secondary:** React Flow for per-module detail panels (best custom-node DX, weak raw scalability - keep visible nodes < ~1-2k).
**Avoid:** Sigma.js (no compound nodes - fights the drill-in model), vis-network (no real compound nodes, slowing maintenance).

**Key implication for 08 (medium):** the renderer does NOT force the deployment choice - Cytoscape runs identically in a browser and a VS Code webview. Recommended: build the graph layer as a framework-agnostic JS module (Cytoscape core + extensions + data adapter), wrap it twice (web app + webview sharing one bundle). Decide web-vs-extension on product grounds, not renderer constraints - ship one host first, add the other later without rewriting the graph layer.

Feeds: 07 (visualization IA - Cytoscape + expand-collapse), 08 (medium - renderer is deployment-neutral).
