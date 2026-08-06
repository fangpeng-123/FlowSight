# FlowSight MVP Spec

Status: **ready-for-agent** · Source: `/to-spec` synthesis of the wayfinder decisions (02–08) + verified 3D prototype (07) + landscape survey.
Tracker idiom: FlowSight has no GitHub-label issue tracker; this spec is published to the local wayfinder corpus and registered in `.scratch/flowsight/map.md`. `ready-for-agent` is recorded here and in the map.

---

## Problem Statement

I have reading difficulty. Understanding a Python codebase I didn't write — or one I wrote long ago — by reading it line by line is slow, painful, and unreliable. I lose the forest for the trees: I can see individual functions but can't hold the data-flow, the interface contracts, the dependency direction, or the risk hotspots in my head at once.

Existing tools don't solve this. The embeddable ones (CodeGraph, jedi, pyright) ship **text** to an LLM, not a visual graph. The ones with a good GUI (Sourcetrail) are dead and copyleft. The SaaS ones (CodeSee) are defunct. None give me a **personal, local, visual, click-to-expand** map of *my* Python codebase that shows the static structure **and** the real data flowing through it at runtime, with the LLM filling in the meaning (contracts, risks, domain entities) that a parser can't derive.

I want to point a tool at my project and *see* the codebase as a floating graph I can drill into — not read it.

## Solution

**FlowSight** is a personal, local web app that builds an interactive **3D knowledge graph** of a Python codebase and serves it in the browser. It fuses three layers:

1. **Static skeleton (exact, instant, trusted)** — `ast` + `importlib`/`pkgutil` + `jedi` extract files, functions, classes, call edges, imports, and module boundaries with line offsets. Zero LLM cost, zero hallucination: the structure is parser-guaranteed.
2. **LLM understanding (advisory, layered, cached)** — eager one-line module summaries at index time; lazy per-function enrichment (purpose, contract, data-flow role, risks) on drill-down; domain entities inferred from function inputs/outputs. Cached per code-hash so only changed functions re-enrich.
3. **Runtime data-flow overlay (actual, observed)** — `viztracer` captures real calls, argument/return values, timings; these are overlaid as **actual-on-expected**: real traces painted onto the LLM-inferred expected flow, divergences highlighted.

The graph is rendered with **3d-force-graph** as a floating, click-to-expand 3D scene: a clean module-level overview that drills into functions and data-flow on demand. Four views (dependency+runtime / data-structures / contracts / risk) are data subsets over one schema. Parser-sourced structure renders as trusted; LLM-sourced annotations render distinctly (advisory); runtime facts render distinctly (actual) — so I always know what to trust.

## User Stories

1. As a developer, I want to point FlowSight at my Python project and have it build a graph, so that I don't have to manually map the codebase.
2. As a developer, I want the structural skeleton built without any LLM call, so that I get an instant, free, trustworthy overview.
3. As a developer, I want the skeleton (files/functions/classes/calls/imports) to be exact and parser-derived, so that I can rely on the structure being correct.
4. As a developer, I want each module to show a one-line purpose summary on first view, so that the graph isn't bare before I drill in.
5. As a developer, I want LLM enrichment to happen lazily only for functions I drill into, so that cost stays bounded to what I actually look at.
6. As a developer, I want enrichment cached per function keyed by its code hash, so that re-indexing after a small change doesn't re-enrich everything.
7. As a developer, I want only functions whose code changed to be re-enriched, so that freshness is automatic and cheap.
8. As a developer, I want a clean overview showing modules and their high-level relationships, so that I'm not overwhelmed on first open.
9. As a developer, I want to click/double-click a module to expand it and see its files, functions, and data flow, so that I can drill in on demand.
10. As a developer, I want to collapse an expanded module back to a single node, so that I can keep the view uncluttered.
11. As a developer, I want to click a function node to select it and see its full details in a side panel, so that I can read its contract without leaving the graph.
12. As a developer, I want to drag to rotate and scroll to zoom the 3D graph, so that I can orient myself in the structure.
13. As a developer, I want the camera to fly to a node I select, so that I can follow a chain through the graph.
14. As a developer, I want a node/edge legend explaining types and colors, so that I can interpret the graph.
15. As a developer, I want a light/dark theme toggle, so that I can match my reading environment.
16. As a developer, I want a dependency view showing calls/imports/contains with the runtime data-flow overlay, so that I see how code is wired and what actually ran.
17. As a developer, I want a data-structures view showing domain entities and produces/consumes/transforms edges, so that I understand the conceptual data model.
18. As a developer, I want a contracts view showing each function's inputs/outputs/errors/boundaries, so that I understand interfaces without reading code.
19. As a developer, I want a risk view showing pitfalls and avoidance strategies ranked by severity, so that I know where to be careful.
20. As a developer, I want to switch views via tabs, so that I can focus on one facet at a time.
21. As a developer, I want to run my app under FlowSight and capture a runtime trace, so that I see actual data flow.
22. As a developer, I want to point FlowSight at an existing trace file, so that I can overlay a trace I already captured.
23. As a developer, I want real argument and return values shown on edges, so that I see actual data, not guesses.
24. As a developer, I want call counts and timings shown, so that I can find hot paths.
25. As a developer, I want actual data flow overlaid on the LLM-inferred expected flow, so that I can spot divergences.
26. As a developer, I want edges that actually fired distinguished from edges that only could fire, so that I see what really happened.
27. As a developer, I want async call chains reconstructed correctly, so that I can trace through async code (only viztracer reconstructs these).
28. As a developer, I want trace events mapped onto the correct function nodes, so that runtime data lands in the right place.
29. As a developer, I want parser-derived structure visually distinct from LLM-derived annotations, so that I know what to trust absolutely vs. judge critically.
30. As a developer, I want runtime-captured facts visually distinct from both, so that I know what's observed truth.
31. As a developer, I want a function's purpose, contract, data-flow role, and risks when I drill in, so that I get full context on demand.
32. As a developer, I want FlowSight to infer domain entities (e.g. AudioChunk, Transcript) from function inputs/outputs, so that I see the conceptual model.
33. As a developer, I want transforms between entities shown (e.g. AudioChunk → Transcript via ASR), so that I see the data pipeline at a glance.
34. As a developer, I want external (3rd-party) symbols distinguished from my own code, so that I know what's mine vs. a dependency.
35. As a developer, I want imports visualized at the module level, so that I see dependency direction.
36. As a developer, I want to search for a function/module/struct/risk by name or content, so that I can jump to it.
37. As a developer, I want a single command to index and serve, so that setup is trivial.
38. As a developer, I want FlowSight to detect my venv, so that imports and third-party symbols resolve correctly.
39. As a developer, I want FlowSight to run locally with no cloud and no auth, so that my code stays private.
40. As a developer, I want to re-index on demand after changes, so that the graph stays current.
41. As a developer, I want a function's signature (params and return type) shown, so that I know its parameters.
42. As a developer, I want the errors/exceptions a function may raise listed, so that I handle them correctly.
43. As a developer, I want preconditions, postconditions, and side-effects noted, so that I understand a function's boundaries.
44. As a developer, I want the risk list ranked by severity, so that I prioritize what to fix or avoid.
45. As a developer, I want to compare expected vs. actual data shapes, so that I catch runtime surprises.
46. As a developer, I want the graph to stay readable and not cluttered, so that my reading difficulty isn't worsened.
47. As a developer, I want selection to highlight a node's neighbors and dim the rest, so that I can focus on a sub-graph.
48. As a developer, I want expand/collapse to preserve node positions where possible, so that drilling doesn't reset my orientation.

## Implementation Decisions

### Architecture (from decision 04 — parser skeleton + LLM enrichment)

The graph is built in two layers plus a runtime overlay. **FlowSight does NOT reuse CodeGraph** for the skeleton; decision 04 deliberately builds the skeleton on stdlib `ast` + `importlib`/`pkgutil` + `jedi` to control the schema (contracts/risks/domain-entities are first-class, which CodeGraph's structural-only model can't express). CodeGraph remains reference prior art, not a dependency.

- **Skeleton module** — input: a project path (and detected venv). Output: trusted nodes/edges with line offsets. `ast` walks every `.py`; `importlib`/`pkgutil` resolve package vs. module vs. site-packages; `jedi` resolves call-site → definition. `pyright`/LSP is an optional precision upgrade behind a flag, not a default.
- **Enrichment module** — input: skeleton nodes + source text. Output: advisory attributes. Eager: one-line `purpose` per module at index. Lazy: per-function `purpose` + `contract` + `data_flow_role` + `risk`, and `DomainEntity` inference, on drill-down. The LLM is called with a token-budgeted context (Aider repo-map approach as reference) — never the whole codebase.
- **Caching** — each enrichment keyed by the function's code hash; hash change invalidates only that entry, re-enriched lazily on next view. Skeleton re-parse is cheap (`ast`) or incremental (`tree-sitter`, if adopted for the UI).
- **Runtime overlay module** — input: a viztracer trace (Chrome Trace JSON) + the skeleton. Output: runtime `data_flow` edges (see schema). Resolves 06: viztracer is the tracer; the user drives a trace by `flowsight trace <cmd>` (FlowSight wraps the entrypoint with viztracer) **or** `flowsight trace --from <file.json>` (ingest an existing trace). Trace events map onto skeleton `Function` nodes by file:line / `f_code` identity; the LLM's inferred `data_flow_role`/`produces`/`consumes` is the *expected* flow; viztracer's captured calls+args are the *actual* flow; divergences (expected edge never fired; unexpected edge fired) are flagged.

### Graph schema (from decision 05; realized in the prototype)

Node types: `Module`, `File`, `Function`, `Class`, `External` (all parser/trusted), `DomainEntity` (LLM/advisory — the prototype's `struct`/dataclass).

Edge types: `contains` (parser), `imports` (parser), `calls` (parser), `references` (parser), `produces`/`consumes`/`transforms` (LLM/advisory), `data_flow` (runtime/actual).

Attributes tagged by source: **parser/trusted** = signature, location (file:line), args, decorators, is_async; **LLM/advisory** = `purpose`, `contract{inputs,outputs,errors,boundaries}`, `data_flow_role`, `risk{category,severity,description,avoidance}`; **runtime/actual** = call_count, arg_values, return_values, timings, trace_id.

The four views are data subsets over this schema: dependency (calls+imports+contains + runtime data_flow overlay), data-structures (DomainEntity + produces/consumes/transforms), contracts (Function + contract), risk (nodes with risk, ranked).

### Trust → visual encoding (from the verified prototype)

Parser/trusted structure renders solid; LLM/advisory renders distinctly; runtime/actual animates. The prototype encodes edge type → visual weight precisely; this decision carries into the build (trimmed from `prototype/index.html`):

```
linkColor : contains=dim grey · calls=grey · produces/consumes/transforms=flow amber
linkWidth : contains=0.7 · calls=1.2 · transforms=3 · produces/consumes=1.8  (unlit=0.4)
arrowLen  : contains=0 · calls=3.2 · produces/consumes=4.5 · transforms=6.5
particles : transforms=5 · produces/consumes=3 · calls/contains=0   (animated flow)
nodeColor : by type (module/file/class/struct/function), risk function=risk red; unlit=dim
```

Node sizing (`nodeVal`): module > file/struct > class > function, risk function bumped. Expand/collapse is hand-rolled over `contains` edges (a set of expanded parent ids; visible = self or expanded parent), since the 3D renderer has no native compound nodes. Selection highlights neighbors and dims the rest.

### Renderer — 3d-force-graph (diverges from decision 03)

**Decision 03 recommended Cytoscape.js; the MVP commits to 3d-force-graph** (3D, the verified prototype, user preference for the floating 3D look). 03's Cytoscape pick is superseded for the MVP renderer. **However, 03's portability advice still holds**: build the graph layer as a framework-agnostic JS module — a *data adapter* (schema graph JSON → renderer model) separate from the 3d-force-graph rendering — so a Cytoscape/2D host can be swapped in later (e.g. for a constrained webview) without rewriting the graph layer. The prototype already separates `visibleData()`/`nodeColor`/`linkColor` (pure data/style) from the `ForceGraph3D()` construction — carry that seam forward.

Practical constraints discovered in the prototype (must be respected): pin **3d-force-graph to v1.80** (the verified version); v1.80 has **no `onNodeDblClick`** — implement double-click detection inside `onNodeClick` (same node within ~350ms). The constructor clears its container (`innerHTML=""`), so all overlays (legend, hint, status) live **outside** the graph container. Theme background requires triple-setting (`backgroundColor` + `renderer.setClearColor` + `scene.background`) plus `resumeAnimation` to repaint after engine stop.

### Medium — local web app (resolves decision 08)

The MVP runs as a **local web app in the browser**: `flowsight index <path>` builds the graph document; `flowsight serve` runs a local web server and opens the 3D view. No auth, single user, local files only. This matches the verified prototype and decision 03's "ship one host first" advice. The graph layer is host-agnostic so a VS Code webview host can be added later without rewriting it. A VS Code extension / desktop app is explicitly out of scope for the MVP.

### Reuse vs build (from the landscape survey)

**Reuse (do not rebuild):** `ast`+`importlib`+`jedi` (skeleton), `viztracer` (runtime trace; the only tracer that reconstructs async chains), `pyright`/LSP (optional contracts precision), `tree-sitter` (only if the UI needs incremental re-parse). **Build (FlowSight's own value):** the 3D visualization, the static+runtime fusion (actual-on-expected overlay), the LLM enrichment layer, the FlowSight graph schema, and the personal-Python ergonomics (one-command index/trace/serve, venv detection). Semgrep (risks facet) and AppMap (runtime alternative) are noted as future options, not MVP dependencies — the MVP derives risks from the LLM and runtime from viztracer.

## Testing Decisions

**What makes a good test here:** test external behavior, not implementation details. The LLM is non-deterministic, so LLM *quality* is never asserted — only that enrichment is correctly keyed, attached, cached, and invalidated. Renderer pixels are never asserted — only the pure data-adapter transform (graph JSON → render model). The single highest-value seam is the build pipeline end-to-end; beneath it, each module gets unit tests on its documented contract.

**Seam 1 — pipeline end-to-end (primary):** a fixture Python project (a small, known codebase — e.g. a mini voice-agent or calculator) goes in; a graph document (JSON conforming to the schema) comes out. Tests assert the graph's nodes/edges/attributes against the expected schema: skeleton correctness (right files/functions/classes/calls/imports), trust tags (parser vs LLM vs runtime), and — with a fixture viztracer trace checked in — runtime `data_flow` edges correctly mapped onto skeleton functions with divergences flagged. The LLM is stubbed with canned responses so the test is deterministic and asserts *attachment* of enrichment, not its content.

**Seam 2 — per-module unit tests (secondary):**
- Skeleton extractor: `ast`/`jedi` extraction correctness on fixture snippets (call-site→def resolution, module boundaries, line offsets).
- Enrichment attacher: enrichment is keyed by code hash, attached to the right node, invalidated on hash change, eager vs lazy triggered correctly (with a stubbed LLM).
- Overlay correlator: a viztracer trace event maps to the correct `Function` node (by file:line / `f_code`); expected-vs-actual divergence detection (fired/not-fired) is correct.
- Viz data adapter: schema graph JSON → renderer model is a pure transform; assert the model for a known graph (node/edge counts, style-by-type, visibility-by-expand-state).

**Prior art:** none in-repo (greenfield). This spec establishes the fixture-project + graph-assertion pattern as the precedent for all future tests.

## Out of Scope

- Multi-user, auth, cloud hosting, pricing — personal tool.
- Non-Python languages — Python-only for this effort.
- VS Code extension / desktop app — web MVP first (decision 08 resolved to web); extension is a future effort.
- Deep/bespoke IDE integration beyond "runs in a browser alongside the IDE."
- LLM output quality assurance — enrichment is advisory and trust-marked; no ground-truth validation of LLM-generated contracts/risks.
- Production performance hardening for very large codebases (>~5–10k nodes) — 3d-force-graph scales to a point; large-codebase layout/perf is future.
- C-extension native-frame tracing (py-spy/scalene) — only viztracer's view in the MVP; py-spy/scalene integration is future.
- Semgrep/AppMap integration — noted as future options; MVP uses LLM for risks and viztracer for runtime.
- Auto file-watch re-indexing — MVP re-indexes on demand; live watch is a future enhancement.

## Further Notes

- **Decision 03 superseded (renderer):** Cytoscape.js → 3d-force-graph for the MVP, per user preference and the verified prototype. 03's "framework-agnostic graph layer, wrap twice" portability advice is retained and strengthened as a renderer-agnostic data adapter.
- **Decision 06 resolved by this spec:** runtime overlay = viztracer (primary; only it reconstructs async chains), driven by `flowsight trace <cmd>` or `--from <file.json>`, mapped onto skeleton `Function` nodes by file:line / `f_code`, rendered as actual-on-expected with divergence highlighting. The "static↔runtime correlation" and "tracing edge cases" fog items (async/generators/C-ext) are addressed: async via viztracer, generators deduped by `f_code`, C-ext out of MVP scope.
- **Decision 08 resolved by this spec:** medium = local web app (browser).
- **Decision 07 (viz IA):** the verified prototype at `.scratch/flowsight/prototype/index.html` is the reference realization. Its data model (module/file/class/struct/function nodes; contains/calls/produces/consumes/transforms edges; 4 dim-tabs = 4 views) and interaction model (click select + fly-to, double-click expand/collapse, neighbor highlight, search, theme toggle) carry directly into the build. The prototype uses static fake data; the build replaces it with the real skeleton + LLM + runtime pipeline, adding the `data_flow` runtime edge and overlay mechanics.
- **Prototype divergence to reconcile:** the prototype animates `produces`/`consumes`/`transforms` (LLM-advisory data flow) as the "flow" particles. In the build, runtime `data_flow` edges (actual) should be the primary animated overlay; the LLM-advisory edges remain styled but the live particle animation should signal *observed* runtime flow, not just inferred flow. Exact visual split is an implementation detail within the trust-encoding decision above.
