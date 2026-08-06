# FlowSight Landscape Survey: Codebase Knowledge-Graph / Call-Graph / Data-Flow Tooling

**Scope:** Prior art for a personal **Python**-codebase tool that builds an interactive
knowledge graph (files / functions / data-flow / contracts / dependencies / risks) using
LLM capability, with a **static skeleton overlaid by runtime traces**, visualized as a
floating click-to-expand graph.

**Method:** Data gathered 2026-08-06 from GitHub repo metadata + READMEs/LICENSE files via
the GitHub API (WebSearch/WebFetch were network-blocked in this environment). Licenses are
the SPDX id reported by GitHub; where GitHub reports `NOASSERTION`, the actual LICENSE text
is noted. Star counts and "pushed_at" are point-in-time signals of maturity/activity, not
endorsements.

---

## TL;DR comparison table

| Tool | Graph build | What it visualizes | Lang focus | License | Embeddable in FlowSight? |
|---|---|---|---|---|---|
| **CodeGraph** (`@colbymchenry/codegraph`) | **Static** (Rust + tree-sitter -> SQLite graph) | None (text to LLM via MCP) | 20+ incl. Python | **MIT** | **Yes** - Node/TS lib + CLI, the static skeleton layer |
| **AppMap** (`appmap-python`) | **Runtime trace** (wrapt instrumentation -> AppMap JSON) | Sequence / dependency / flame maps (separate web app) | Python (+JS/Ruby/Java/Go) | MIT + **Commons Clause** | **Yes** for recording (pip pkg); viz app is separate |
| **CodeSee** (codesee.io) | Static + runtime (SaaS, closed) | Code maps / dependency maps | Multi | **Proprietary / defunct** | No (not OSS; company wound down ~2023-24) |
| **Sourcegraph / Cody** | Static via **SCIP** indexers + embeddings; LLM in Cody | Code search UI, references (not a graph GUI) | Multi | Apache-2.0 historically; main repo now private/source-available | Partial - SCIP format + scip-python reusable; platform not embeddable |
| **Swimm** | LLM-generated docs tracked to code | Docs (not a graph) | Multi | Proprietary SaaS | No (docs tool, not a graph) |
| **jedi** | Static parse (parso) + type inference, on-demand refs | None (library) | Python | MIT (NOASSERTION on GH) | **Yes** - pure-Python lib, references/goto/types |
| **pyright / Pylance** | Static type analysis (own parser) | None (LSP diagnostics) | Python | pyright **MIT**; Pylance proprietary | **Yes** (pyright) for types/contracts |
| **tree-sitter** | **Parse** to CST (incremental) - not a graph itself | None (library) | 30+ grammars | **MIT** | **Yes** - the parsing foundation |
| **Semgrep** | Pattern-based static analysis / taint dataflow | Findings in CI/CLI/cloud | Multi incl. Python | **LGPL-2.1** (OSS engine) | Call as external CLI (copyleft) for the "risks" facet |
| **Sourcetrail** | Static parse -> call/inherit/usage graph | **Interactive GUI graph** (click-to-expand, active node) | C/C++/Java/Python/... | **GPL-3.0**, **archived** (Dec 2021) | No (dead, copyleft) - but the **UX reference design** |
| **bloop** | tree-sitter + embeddings (semantic search) | CLI/chat results | Multi | Apache-2.0, **archived** (Dec 2024) | Maybe (Rust) - semantic-search prior art |
| **Aider** | tree-sitter "repo map" (ranked symbol graph) for LLM ctx | None (terminal) | Multi | Apache-2.0 | Ideas/code reusable (repo-map approach) |
| **continue** | Embeddings codebase indexing + LLM | IDE chat (VS Code/JetBrains) | Multi | Apache-2.0 | Ideas reusable (indexing approach) |
| **CodeBendKit/codeseek** | Static call graph (Rust) + hybrid semantic search | None (MCP text to agent) | 7 incl. Python | MIT | Alternative to CodeGraph (smaller, +semantic search) |
| **pydeps** | Static import graph | Graphviz dot | Python | BSD-2-Clause | Yes (lib) - but module-level only |
| **pyan / pycallgraph / pycg** | pyan=static AST; pycallgraph=runtime settrace | Graphviz dot | Python | MIT-ish / archived | Reference only (narrow, stale) |

---

## A. Code knowledge-graph / MCP tools for LLM agents (the closest neighbors)

### CodeGraph - `@colbymchenry/codegraph`
- **Repo:** `colbymchenry/codegraph` - **64,820 stars**, MIT, pushed 2026-08-05 (very active).
  NPM: `@colbymchenry/codegraph@1.0.0` (created 2026-01-18). Homepage: colbymchenry.github.io/codegraph.
- **What it does:** "Local-first code intelligence for AI agents (MCP)." A pre-indexed code
  knowledge graph that auto-syncs on code changes; exposes MCP tools so Claude Code / Cursor /
  Codex / Gemini / OpenCode / etc. get surgical context with fewer tokens and tool calls.
  Platform pitch: per-PR "what to test, what breaks, which flows affected."
- **How it builds the graph - STATIC:** A native **Rust kernel** parses source with
  **tree-sitter** grammars compiled into it, extracting **nodes** (functions, classes, methods)
  and **edges** (calls, imports, extends, implements) for 20+ languages. Persisted in a
  **SQLite knowledge graph** (symbols, edges, files, **FTS5** full-text search). Framework-aware
  (web routes -> handlers; iOS/RN/Expo cross-language bridging). Auto-sync via native OS file
  watchers (FSEvents/inotify/ReadDirectoryChangesW). **No runtime traces, no LLM in the build**
  (the LLM only consumes the graph).
- **What it visualizes:** **Nothing graphical.** It returns verbatim source + call paths +
  blast-radius as *text* to the agent. MCP surface is a single tool `codegraph_explore`
  (others - `node`, `search`, `callers`, `callees`, `impact`, `files`, `status` - unlisted by
  default, available via CLI/env).
- **Embeddability - HIGH:** Programmatic API from npm:
  `import CodeGraph from '@colbymchenry/codegraph'` -> `init/indexAll/searchNodes/getCallers/
  getImpactRadius/buildContext/watch`. Lower-level exports: `DatabaseConnection`, `QueryBuilder`,
  `getDatabasePath`, grammar loaders, `FileLock`. Runs on Node 22.5+ (uses `node:sqlite`);
  embeddable in an Electron main process. CLI/MCP server are self-contained (bundled runtime,
  no Node needed). **MIT, 100% local, no API keys.**
- **Fit for FlowSight:** This is the most directly reusable piece. It *is* a static code
  knowledge graph with Python support, embeddable, MIT, local. FlowSight can stand on CodeGraph
  for the entire static-skeleton layer (files/functions/calls/imports/impact) and add the
  runtime-trace overlay + LLM enrichment + its own floating-graph UI on top. Caveat: black-box
  Rust kernel (you trust its extraction; can't easily extend its graph schema for FlowSight's
  "contracts/risks" facets without the FTS/SQLite side-joins). The SQLite graph is queryable,
  so FlowSight can read it directly and enrich.

### CodeBendKit/codeseek
- **Repo:** `CodeBendKit/codeseek` - 821 stars, MIT, Rust, pushed 2026-08-02.
- **What it does:** "Rust-powered code intelligence CLI for AI coding agents. Builds call graphs
  and **hybrid semantic search indexes** (Dense + Sparse + RRF + Reranker) across 7 languages.
  Ships as native MCP tools for Claude Code and Codex CLI."
- **How:** Static parse (Rust) for the call graph **+ embeddings** for semantic search (the
  differentiator vs CodeGraph). No runtime, no LLM in the graph build (LLM consumes).
- **Visualizes:** None (MCP text).
- **Embeddability:** MIT, Rust, MCP - comparable to CodeGraph but smaller community and adds
  semantic search. A viable alternative or complement (CodeGraph for the structural graph,
  codeseek's hybrid-search pattern for FlowSight's LLM retrieval).

---

## B. Runtime trace + data-flow (the overlay layer)

### AppMap - `getappmap/appmap-python`
- **Repo:** `getappmap/appmap-python` - 104 stars, Python, pushed 2026-07-10. Homepage appland.org.
- **What it does:** Python package that records **AppMaps** - a data format recording (a) code
  structure (modules/classes/methods), (b) code execution events (function calls and returns),
  (c) code metadata (repo, commit, labels). "More granular than a performance profile, less
  granular than a full debug trace. Designed for understanding design intent, structure, and key
  data flows."
- **How it builds the graph - RUNTIME TRACE:** Instruments Python via **wrapt** (vendored) at
  import/run time, records actual call events + parameters/return values + object identity ->
  AppMap JSON. Records what *actually* executes (the runtime overlay FlowSight wants).
- **What it visualizes:** The separate **AppMap app** (web + VS Code extension) renders sequence
  diagrams, dependency maps, flame graphs, trace detail from the recorded AppMap JSON.
- **License:** **MIT + Commons Clause** ("Sell" restriction: can't sell a product whose value
  derives substantially from the Software). Fine for personal/internal use; a commercial FlowSight
  product would need to negotiate or reimplement the recorder.
- **Embeddability - HIGH for recording:** `pip install appmap` instruments any Python program;
  the AppMap JSON format is open. FlowSight can use appmap-python to capture runtime call/data
  traces and overlay them on its static graph. Visualization app is separate (not embeddable as a
  lib, but the JSON is yours to render).
- **Fit for FlowSight:** The runtime-trace overlay layer, purpose-built for Python. Also has
  JS/Ruby/Java/Go agents if FlowSight ever expands. The Commons Clause is the one legal snag for a
  shipped product; for a *personal* tool it's a non-issue.

---

## C. Static analysis / type / reference / risk primitives

### tree-sitter
- **Repo:** `tree-sitter/tree-sitter` - 26,557 stars, **MIT**, Rust, pushed 2026-08-05.
- **What:** Incremental parsing system -> concrete syntax trees (CST). Not a graph itself, but the
  foundation for building symbol/edge graphs (you walk the CST). 30+ maintained grammars incl.
  `tree-sitter-python`. Python bindings (`tree-sitter`, `tree-sitter-python`).
- **Embeddability - HIGHEST:** MIT, tiny, fast, incremental, bindings everywhere. The de-facto
  parsing layer used by CodeGraph, Aider, bloop, Neovim, GitHub code search. FlowSight should
  either use tree-sitter directly or inherit it via CodeGraph.

### jedi
- **Repo:** `davidhalter/jedi` - 6,168 stars, Python, pushed 2026-07-09. License: MIT
  (GitHub reports NOASSERTION because the LICENSE file combines MIT + PSF).
- **What:** Awesome autocompletion / static analysis / refactoring library for Python. Owns its
  own parser (`parso`). Provides goto-definition, find-references, type inference, signatures -
  i.e. a **reference graph on demand**.
- **How - STATIC:** parso AST + type inference (with stubs). No graph DB; computes per-query.
- **Visualizes:** nothing (library; powers IPython, vim, emacs).
- **Embeddability - HIGH:** pure-Python, MIT, the canonical Python static-analysis lib. FlowSight
  can use jedi for precise symbol resolution / references / call targets where CodeGraph's
  tree-sitter extraction is too coarse (e.g. resolving dynamic attribute access).

### pyright / Pylance
- **Repo:** `microsoft/pyright` - 15,566 stars, Python/TS, pushed 2026-08-05. License: pyright
  **MIT** (GitHub reports NOASSERTION). Pylance (the VS Code extension) is **proprietary/closed**,
  built on pyright.
- **What:** Static type checker for Python. Own parser, cross-file type inference, very precise.
  Emits diagnostics + type info + cross-references via LSP.
- **How - STATIC:** whole-program type analysis.
- **Visualizes:** nothing (LSP server; editor squiggles).
- **Embeddability - MEDIUM-HIGH:** pyright is MIT, npm package (`pyright`), runnable as CLI/lib.
  Heavy (Node/TS) and oriented to diagnostics, but gives FlowSight the **"contracts" facet**
  (precise signatures, types, parameter info) for free. Pylance is off-limits (proprietary).

### Semgrep
- **Repo:** `semgrep/semgrep` - 16,124 stars, OCaml, pushed 2026-08-06. License: **LGPL-2.1**
  (OSS Community edition); Semgrep Pro (interfile dataflow/taint) is proprietary.
- **What:** Lightweight static analysis - find bug/security variants with patterns that look like
  source code. Multi-language; large Python rule pack (Bandit-equivalent, OWASP, etc.).
- **How - STATIC:** pattern-matching + (Pro) taint/dataflow analysis. Not a graph DB, but produces
  structured findings (rule id, path, lines, severity, dataflow path).
- **Visualizes:** findings in CI/CLI/Semgrep Cloud (no graph GUI).
- **Embeddability - LOW (link), MEDIUM (CLI):** LGPL-2.1 copyleft means don't statically link into
  a non-LGPL FlowSight. Invoke as an external CLI/subprocess and consume JSON output - that gives
  FlowSight the **"risks" facet** (security/bug/anti-pattern hotspots) without license entanglement.

---

## D. Code-graph visualization GUI prior art (the UX reference)

### Sourcetrail - `CoatiSoftware/Sourcetrail`
- **Repo:** `CoatiSoftware/Sourcetrail` - 16,491 stars, C++, **GPL-3.0**, **ARCHIVED** (last push
  2021-12-13). Homepage sourcetrail.com.
- **What:** "Free and open-source interactive source explorer." Builds a code graph (calls,
  inheritance, usage, overrides) and renders it as an **interactive GUI**: a graph view where you
  click a node and it becomes the active focus, showing neighbors; expand/collapse; cross-language.
- **How - STATIC:** own parser frontends (ctags + language-specific) -> graph -> native C++ GUI.
- **Visualizes:** THE closest existing realization of FlowSight's "floating click-to-expand graph."
  Node-active-focus + edge traversal UX is exactly the FlowSight vision (minus runtime + LLM).
- **Embeddability - NONE:** GPL-3.0 copyleft, archived/dead, C++ native GUI. Cannot embed. But
  **study its UX** - it's the reference design for FlowSight's visualization. (There have been
  community revival forks; none have replaced it.)

### CodeSee (codesee.io)
- **Status:** The original CodeSee was a **SaaS** (not OSS) for "Code Maps" - auto-generated maps
  of codebase structure/logic using static + runtime data, plus PR-review features. The company
  wound down / pivoted and is effectively **defunct (~2023-24)**. No main product repo is OSS
  (only `Codesee-io/oss-port` and `remote-companies` remain - unrelated). Unrelated newer tools
  share the name (e.g. `CodeBendKit/codeseek`, `Kaka-cheeper/codeSee`).
- **Fit:** Prior art for "auto-generated code map" and "runtime-informed maps." Nothing to embed.

### pydeps - `thebjorn/pydeps`
- **Repo:** `thebjorn/pydeps` - 2,106 stars, Python, **BSD-2-Clause**, pushed 2026-08-05.
- **What:** Python **module** dependency graphs (import-level, not function-level). Emits Graphviz
  dot. Embeddable pure-Python lib. Useful as a cheap "file/module dependency" sub-view, but too
  coarse for FlowSight's function/data-flow graph.

### pyan / pycallgraph / pycg (Python-specific, narrow)
- **pyan:** static AST-based Python call graph -> Graphviz. Stale-ish, narrow.
- **pycallgraph:** runtime `sys.settrace` call graph -> Graphviz/PNG. Old/archived.
- **pycg:** dynamic call graph generation. Niche.
- **Fit:** Reference only. CodeGraph + AppMap supersede these for FlowSight's needs.

---

## E. LLM codebase-understanding platforms (LLM-assisted code understanding)

### Sourcegraph / Cody
- **Status:** Sourcegraph is the code-search + code-intelligence platform. The main
  `sourcegraph/sourcegraph` repo now returns **Not Found** on GitHub - Sourcegraph restructured
  (~2025), made the core source-available/private, and pivoted to **Amp** (its coding agent) +
  Sourcegraph.com. Historically Apache-2.0 for some OSS parts; the platform is no longer freely
  embeddable.
- **How it builds the graph - STATIC (precise) + embeddings:** **SCIP** (Sourcegraph Code
  Intelligence Protocol, successor to LSIF) - language indexers emit precise symbol/reference data.
  `scip-python` is the OSS Python indexer. Cody adds embeddings + LLM for Q&A.
- **Visualizes:** code search UI, references panel (not a graph GUI).
- **Embeddability:** The **SCIP format is open** and `scip-python` is reusable - FlowSight could
  consume SCIP indexes as an alternative/complement to CodeGraph for precise references. The
  Sourcegraph platform/Cody itself is not embeddable.

### Aider - `Aider-AI/aider`
- **Repo:** `Aider-AI/aider` - 47,971 stars, Python, **Apache-2.0**, pushed 2026-05-22.
- **What:** AI pair programming in the terminal.
- **How - STATIC + LLM:** Builds a **"repo map"** using tree-sitter: a ranked graph of symbol
  definitions + call/import references, token-budgeted so the LLM gets the most relevant code
  context. Not visualized as a graph (fed to the LLM).
- **Embeddability:** Apache-2.0 Python - the repo-map construction code/approach is reusable prior
  art for "tree-sitter symbol graph sized for an LLM context window" (directly relevant to
  FlowSight's LLM enrichment retrieval).

### bloop - `bloopai/bloop`
- **Repo:** `bloopai/bloop` - 9,506 stars, Rust, **Apache-2.0**, **ARCHIVED** (Dec 2024).
- **What:** Fast code search; natural-language code search via embeddings (LLM-assisted).
- **How - STATIC + embeddings:** tree-sitter parsing + vector embeddings for semantic retrieval.
- **Embeddability:** Apache-2.0 Rust, but archived. Reusable as prior art / code reference for
  FlowSight's semantic-search-over-codebase layer (if it doesn't just reuse codeseek).

### continue - `continuedev/continue`
- **Repo:** `continuedev/continue` - 35,338 stars, TypeScript, **Apache-2.0**, pushed 2026-08-05.
- **What:** Open-source coding agent (VS Code / JetBrains). Codebase indexing via embeddings +
  LLM (`@codebase`, etc.).
- **Embeddability:** Apache-2.0 but it's an IDE extension, not a library. Reusable as
  approach-reference for embeddings-based codebase indexing.

### Swimm
- **Status:** SaaS (proprietary). Documentation tool that uses LLM to auto-generate/maintain docs
  that track code changes ("docs as code").
- **Fit:** Not a graph/call-flow tool. The only transferable idea is "knowledge that auto-syncs as
  code changes" - which CodeGraph already does for the structural graph. Nothing to embed.

---

## Reuse vs Build

**REUSE (stand on these - don't rebuild):**

1. **tree-sitter (+ tree-sitter-python) for parsing** - MIT, the universal foundation; either use
   directly or inherit via CodeGraph. Rationale: nobody hand-rolls a Python parser and wins.
2. **CodeGraph (`@colbymchenry/codegraph`) as the static skeleton + graph store** - MIT, embeddable
   Node/TS lib, local SQLite graph of symbols/edges/impact, Python support, auto-sync. Rationale:
   this *is* FlowSight's static layer; rebuilding it wastes the differentiator (LLM + runtime +
   viz). Read its SQLite graph directly to enrich.
3. **AppMap (`appmap-python`) for the runtime-trace overlay** - pip-installable Python runtime
   recorder producing open AppMap JSON (calls, returns, params, data flow). Rationale: purpose-built
   for exactly the runtime overlay FlowSight wants; far better than hand-rolling `sys.settrace`.
   (For a *shipped* product, revisit the Commons Clause; for a personal tool, non-issue.)
4. **pyright (or jedi) for the "contracts" facet** - MIT, precise Python types/signatures.
   Rationale: signatures/types/parameter contracts for free; pyright for precision, jedi for a
   pure-Python lightweight option.
5. **Semgrep (external CLI) for the "risks" facet** - invoke as subprocess, consume JSON findings.
   Rationale: huge Python security/bug rule set; LGPL-2.1 keeps it out-of-process (no copyleft
   contamination) but still usable.
6. **SCIP / `scip-python` (optional) for precise references** - open format + OSS Python indexer.
   Rationale: a complementary, higher-precision reference source if CodeGraph's tree-sitter edges
   are too coarse for dynamic Python.
7. **Aider's repo-map approach (reference) for LLM context sizing** - token-budgeted tree-sitter
   symbol graph. Rationale: proven recipe for feeding a code graph to an LLM within a context
   window (directly serves FlowSight's LLM enrichment retrieval).

**BUILD (FlowSight's own value - no tool does this):**

1. **The visualization** - floating, click-to-expand, zoomable graph UI. Rationale: every
   embeddable graph tool (CodeGraph, codeseek, jedi, pyright) ships *text*, not a GUI; Sourcetrail
   (the only good GUI prior art) is GPL + archived + C++. The graph UI is the product surface.
   (Use a web graph lib - e.g. Cytoscape.js / vis-network / d3-force / react-flow - on top of the
   graph data; see sibling `graph-viz.md`.)
2. **Static + runtime fusion** - overlay AppMap traces onto CodeGraph's static nodes; compute
   "edges that actually fired," observed call frequencies, real data shapes, hot paths. Rationale:
   the core thesis ("static skeleton overlaid by runtime traces") is novel; no tool fuses these.
3. **LLM enrichment layer** - semantic contracts, risk inference, node/edge summarization,
   "explain this flow," novel semantic edges (e.g. "this function writes to the user table"),
   natural-language graph queries. Rationale: the LLM differentiator; existing LLM tools do
   search/chat, not *annotated knowledge-graph* authoring.
4. **The FlowSight graph schema** - extend CodeGraph's symbol/edge model with contracts, risks,
   data-flow facts, runtime evidence, and LLM-authored annotations as first-class nodes/edges.
   Rationale: CodeGraph's schema is structural only; FlowSight's facets need their own model
   (layered on top, reading CodeGraph's SQLite as input).
5. **Personal / Python ergonomics** - one-command index + trace + visualize for a personal repo;
   opinionated Python defaults (venv detection, pytest/test-trace harness, Django/Flask/FastAPI
   route awareness). Rationale: existing tools are generic or SaaS; FlowSight's personal-Python
   fit is the user-facing wedge.

**AVOID (dead ends):** CodeSee (defunct, not OSS), Sourcetrail (dead, GPL - UX reference only),
bloop (archived), pycallgraph/pyan/pycg (narrow/stale, superseded by CodeGraph+AppMap), Pylance
(proprietary), Swimm (docs not graphs).
