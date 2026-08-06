# 04 - Core architecture: how the LLM builds the graph

Type: grilling · Status: resolved · Blocked by: 01 (in-flight), 02 (resolved)

## Question

How does FlowSight's LLM-centric graph building actually work? The destination grilling settled "leverage model capability for structural querying and graph drawing" but left the architecture open. Decide between (and sharpen): LLM-only / parser skeleton + LLM enrichment / agentic exploration. Weigh cost, determinism, scale beyond one context window, and how each option accommodates the runtime overlay (ticket 06). Keystone - 05, 06, 07 all depend on it.

## Answer

**Decision: Parser skeleton + LLM enrichment (Architecture A), with hybrid eager/lazy enrichment.**

The graph is built in two layers:

1. **Skeleton (deterministic, instant, exact):** `ast` + `importlib`/`pkgutil` + `jedi` extract the full structure - files, functions/classes, call edges (call-site -> def, resolved by jedi), imports, module boundaries - with line offsets to anchor runtime traces. Zero LLM cost, scales to any project size, zero hallucination. This is what makes the graph reliable (critical for the user's reading difficulty: wrong structure is worse than none).

2. **Understanding (LLM, layered):**
   - **Eager, lightweight:** at index time, the LLM produces a one-line summary per module/file (cheap, fast) so the graph isn't bare on first view.
   - **Lazy, deep:** when the user drills into a function (click-to-expand), the LLM enriches THAT node with purpose, contract (inputs/outputs/errors/boundaries), data-flow role (what data flows in/out, what it transforms), and risks/pitfalls. Bounded cost - only what's viewed is enriched.

**Caching & freshness:** each enrichment is cached per-function, keyed by the function's code hash. When code changes, only that function's hash changes -> only that entry is invalidated and re-enriched lazily on next view. Skeleton re-parse is cheap (`ast`) or incremental (`tree-sitter`, if adopted for the UI).

**Scale:** the parser carries full structure for free; LLM cost stays bounded because enrichment is lazy + cached. No "feed the whole codebase into one context window" problem - the thing that kills LLM-only/agent approaches on big projects.

**Determinism / hallucination:** the skeleton (call graph, imports, defs) is exact - parser-derived, never LLM. Only the *annotations* (purpose/contract/risks) are LLM-derived and can be wrong; they'll be visually marked as model-generated so the user trusts structure and judges annotations. Hallucination concern is contained: structure is trustworthy, annotations are advisory.

**Connection to runtime overlay (06):** the LLM infers the *expected/likely* data-flow (what should flow between functions, from reading code); `viztracer` captures the *actual* data-flow (what really flowed, with real values, in a given run). The overlay shows **actual-on-expected**: real traces painted onto the inferred flow, divergences highlighted. Exact overlay mechanics deferred to 06.

**Differentiation from CodeGraph:** CodeGraph is agentic LLM exploration (option C). FlowSight differentiates by being a *reliable, visualized* graph - parser-guaranteed structure + LLM meaning + runtime-truth overlay - not another agentic explorer.

**Feeds / graduates:** 05 (graph schema - the exact enrichment fields & the four views) is now unblocked. 06 (overlay mechanics) takes the actual-on-expected framing. Fog items "scale", "LLM determinism/cost", "freshness" are largely resolved by this decision; "static↔runtime correlation" and "tracing edge cases" remain for 06.

## Worklog

- Claimed; resolved via grilling (architecture A + hybrid trigger). 01 (landscape) still in-flight; its findings, when landed, should be reviewed against the "differentiation from CodeGraph" point but are not expected to overturn this decision.
