# FlowSight - Wayfinder Map

`wayfinder:map` · tracker: local markdown (`.scratch/flowsight/`)

## Destination

A build-ready spec for **FlowSight**: a personal Python-codebase tool that builds an interactive knowledge graph - files, functions, data-flow, interface contracts, dependency direction, and risk hotspots - by **leveraging LLM capability for structural querying and graph construction**, with a **static skeleton overlaid by runtime data-flow traces**, visualized as a **floating, click-to-expand graph** (clean overview, drill into modules for detail).

The map is done when these are all decided - enough to start building an MVP:
- core architecture (how the LLM builds the graph),
- graph schema & views (what nodes/edges/layers),
- runtime data-flow overlay technique,
- visualization information architecture + tech,
- medium (local web app vs IDE extension).

## Notes

- **Domain:** Python code analysis; LLM-assisted code understanding; interactive graph visualization; runtime tracing.
- **Skills every session should consult:** `/grilling` + `/domain-modeling` (default for decisions), `/prototype` (for "how should it look"), `/research` (for outside-codebase facts).
- **Standing preferences (from destination grilling):**
  - Personal tool first - runs on the user's machine, for the user. Not a product.
  - Python-only; vision is to support *any* Python project (the ASR->LLM->TTS voice-agent example is an illustration of the kind of flow to visualize, not a v1 scope limit).
  - LLM-centric: the model does the structural querying and graph drawing (not a pure deterministic parser).
  - Hybrid: static graph as skeleton + runtime data-flow overlay.
  - Visual-first: the user has reading difficulty; graphs + IDE search beat line-by-line reading. Keep the main view clean; expand modules on demand.
- **Tracker mechanics:** Map = this file; tickets = `issues/NN-<slug>.md`; research findings = `research/<name>.md`. Claim = `Status: claimed`; resolve = append `## Answer` + `Status: resolved` + add a Decisions-so-far line here.

## Decisions so far

- [02 Python analysis & tracing primitives](issues/02-python-primitives-research.md) - skeleton: `ast` + `importlib` + `jedi` (pyright optional); overlay: `viztracer` + `sys.monitoring` + `sys.audit` + `py-spy`/`scalene` + targeted monkey-patch; only viztracer fixes async chains, only py-spy/scalene see C frames.
- [03 Graph visualization tech](issues/03-graph-viz-research.md) - **Cytoscape.js** (native compound + expand-collapse, MIT, runs in browser AND VS Code webview); G6 v5 alt for >10k nodes; React Flow for detail panels; renderer is deployment-neutral so 08 decides on product grounds.
- [04 Core architecture](issues/04-core-architecture.md) - **parser skeleton (`ast`+`jedi`, exact/free/scales) + LLM enrichment** (eager module summaries + lazy deep per-function on drill-down), cached per code-hash; skeleton trustworthy, annotations advisory; runtime overlay = actual(viztracer)-on-expected(LLM). Unblocks 05.
- [05 Graph schema & views](issues/05-graph-schema-views.md) - nodes Module/Function/Class/External/**DomainEntity**(LLM); edges calls/imports/contains/references/produces/consumes/transforms/data_flow; attrs tagged parser(trusted)/LLM(advisory)/runtime(actual); 4 views = data subsets (dependency+runtime-overlay / data-structures=LLM domain entities / contracts / risk list). Unblocks 07.

## Build spec (ready-for-agent)

- **[FlowSight MVP Spec](../../doc/spec/flowsight-mvp-spec.md)** - build-ready PRD synthesized via `/to-spec` from decisions 02–08 + the verified 3D prototype (07) + landscape survey. Status: `ready-for-agent`. Resolves three open items:
  - **08 (medium) → local web app (browser).** Ship one host first; graph layer stays host-agnostic for a future webview.
  - **06 (runtime overlay) → viztracer actual-on-expected.** `flowsight trace <cmd>` or `--from <file.json>`; trace events mapped onto skeleton `Function` nodes by file:line / `f_code`; async via viztracer, generators deduped by `f_code`, C-ext out of MVP scope.
  - **03 (renderer) → 3d-force-graph (supersedes Cytoscape for the MVP).** User preference + verified prototype. 03's framework-agnostic-graph-layer advice retained as a renderer-agnostic data adapter. Pin 3d-force-graph v1.80; no `onNodeDblClick` (detect in `onNodeClick`); overlays outside the graph container; triple-set theme bg.

## Not yet specified

- ~~**Static↔runtime correlation**~~ - resolved by the MVP spec (06 above): viztracer actual-on-LLM-expected, mapped by file:line / `f_code`.
- **Tracing edge cases** - async (only viztracer reconstructs chains), generators (dedupe by `f_code`), C extensions (only py-spy/scalene see native frames). Async + generators covered by the spec; C-ext deferred (out of MVP scope).

## Out of scope

- Multi-user, auth, cloud hosting, pricing - personal tool.
- Non-Python languages - Python-only for this effort.
- Deep/bespoke IDE integration beyond "runs alongside" - until the medium (ticket 08) is decided; if an IDE extension is chosen, a focused subset may return as a fresh effort.
