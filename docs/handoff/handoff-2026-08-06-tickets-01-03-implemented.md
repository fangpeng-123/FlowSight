# Handoff — tickets 01-03 implemented (2026-08-06)

For the next agent picking up FlowSight. Read this alongside the artifacts it references — it does not repeat them.

## Where things stand

- **Branch:** `main` · **Last commit:** `a1efa41` "feat: 实现 tickets 01-03 -- 骨架提取 / 本地 3D 渲染 / LLM 富化" · **Working tree:** clean.
- **Done & committed:** tickets **01 (skeleton)**, **02 (serve + 3D render)**, **03 (LLM enrichment + trust marking + caching)**. See `git show a1efa41` for the full diff.
- **NOT started (by explicit user direction — "任务至多做到三，然后就结束"):** tickets **04 (domain entities + four views + search)** and **05 (runtime data-flow overlay)**. Do not assume they were forgotten; they were deliberately deferred.
- **Tests green:** 37 Python (`tests/test_schema|venv|skeleton|pipeline|enrich.py`) + 10 JS adapter (`tests/test_adapter.mjs`, `node:test`).

Reference, don't re-derive:
- Spec & tickets: `docs/spec/flowsight-mvp-spec.md`, `.scratch/flowsight/tickets/01..05-*.md`
- Decisions & map: `.scratch/flowsight/issues/02..08-*.md`, `.scratch/flowsight/map.md`
- Prior handoff (build-ready spec): `docs/handoff/handoff-2026-08-06-spec-tickets-ready-to-build.md`

## What the next session should focus on

Per the user's scope, the frontier is now **tickets 04 and 05** (dependency: `01->02->03->04`; `02->05`; both 04 and 05 are unblocked). The MVP spec + each ticket file (`04-domain-entities-views.md`, `05-runtime-overlay.md`) define the checklist — work from those, don't re-spec.

Additionally, the `/code-review` run on `a1efa41` surfaced **deferred items** (noted in the commit body) that are natural polish to pick up before or alongside 04/05:

- `extractor.py` — 11-param cluster through `_walk_file`/`_visit_body`/`_define_func`/`_define_class` → bundle into a `WalkCtx` (Data Clump).
- `web/adapter.js` — `linkColor`/`linkWidth`/`arrowLen`/`particles` each switch on `link.type` → one `LINK_STYLE` table (Repeated Switches; note this is the tested seam — update `test_adapter.mjs`).
- 3D scene does not visually distinguish advisory (LLM) from trusted (parser) nodes — distinction is panel-only today (ticket 03 asked for "visually distinct").
- `contains` edges carry no `location` (ticket 01 listed them among edges that should carry line offsets).
- `venv.detect()` reflects FlowSight's interpreter, not the target project's (core external classification still works via `project_modules` + `sys.stdlib_module_names`).
- Module-level call sites are dropped (`caller_id is None` skipped in `extractor.py`) — a deliberate simplification, revisit if a project needs top-level calls.

## Environment & how to run

- **Python env:** conda env `myenv` (Python 3.11.15). Install/deps via **Tsinghua mirror** (user standing instruction). `jedi>=0.19` is the one runtime dep.
- **Run tests:** `conda run -n myenv python -m pytest tests/ -q` · `conda run -n myenv node --test tests/test_adapter.mjs`
- **Run the app:** `conda run -n myenv python -m flowsight.cli serve tests/fixtures` (opens browser at `127.0.0.1:8000`). Index only: `flowsight index <path> -o graph.json`.
- **LLM config (optional):** env vars `FLOWSIGHT_LLM_API_KEY`, `FLOWSIGHT_LLM_BASE_URL` (default DashScope compatible-mode), `FLOWSIGHT_LLM_MODEL` (default `qwen-plus`). With no key, enrichment falls back to docstrings (no network). The `StubLLMClient` is used in tests — never assert LLM content, only keyed/attached/cached/invalidated.
- **Screenshots:** this model has no native image reading — use the global `vision.js` script per the global `CLAUDE.md` (`node "C:/Users/fang/.claude/scripts/vision.js" "<path>" "用中文描述"`).
- **Note on `conda run -n myenv python -c`:** multi-line `-c` strings fail under conda; write a temp `.py` file and run that instead.

## Critical gotchas (learned the hard way — verify before relying)

- **jedi:** use `infer()`, not `goto()` (goto returns the import-binding, not the definition). For method calls, infer the receiver → class instance → look up the method by name. stdlib via `sys.stdlib_module_names`.
- **`EnrichCache` defines `__len__`** → an empty cache is **falsy**, so `if cache:` skips `put`/`get`. Always use `if cache is not None:`. (Bug fixed in `a1efa41`; don't reintroduce.)
- **3d-force-graph v1.80 constraints:** no `onNodeDblClick` (detect double-click in `onNodeClick` ~350ms); overlays must live outside `#cy` (the constructor clears its innerHTML); theme bg is triple-set (`backgroundColor` + `renderer.setClearColor` + `scene.background`).
- **Renderer seam:** `web/adapter.js` is the pure, tested, renderer-agnostic data adapter (decision 03 portability). All graph/style logic goes through it; `app.js` only consumes. Don't bypass it (the review caught `doSearch` reimplementing `adapter.search` — now fixed).
- **Trust model:** `node.origin` stays `parser` (structure is parser-derived); LLM advisory fields are layered on and tagged via `attrs["purpose_origin"]` (`llm`/`docstring`/`fallback`) and `attrs["enriched"]`. No node carries `origin="llm"` yet — `DomainEntity` (ticket 04) is the intended first true `origin=llm` node.
- **Caching:** per-function `code_hash` (sha256 of source segment, 16 chars) is the cache key; a hash change invalidates only that entry. Module content-hash is over the module's files' source.

## Code map (entry points)

- `src/flowsight/schema.py` — dataclasses + JSON round-trip + trust/edge constants.
- `src/flowsight/skeleton/` — `extractor.py` (two-pass AST walk + jedi call resolution), `resolver.py` (jedi `infer` + `code_hash` + `func_source_segment`), `venv.py` (stdlib/site-packages classification).
- `src/flowsight/enrich/` — `llm.py` (Protocol + Stub + OpenAI-compatible + `from_env`), `cache.py` (`EnrichCache`), `attacher.py` (`enrich_eager` modules / `enrich_function` lazy).
- `src/flowsight/server/` — `app.py` (`GraphState` runs `enrich_eager` at init/reindex; stdlib `http.server`), `enrich_api.py` (`/api/enrich?node=<id>`).
- `src/flowsight/web/` — `adapter.js` (tested seam), `app.js` (3D + panel), `index.html`/`style.css`, vendored `lib/3d-force-graph.min.js` + `lib/three.min.js`.
- `src/flowsight/cli.py` — `index` (now runs `enrich_eager`) / `serve` / `trace` (stub, ticket 05).
- `tests/fixtures/voice_agent/` — the indexed sample project (ASR→LLM→TTS pipeline); all imports absolute `from voice_agent.X import Y`.

## Suggested skills

- **`/implement`** — to build tickets 04 and 05. Re-confirm scope with the user first (they previously capped at 03; 04/05 were deferred, not forbidden).
- **`/code-review`** — run after each ticket lands (two-axis: standards + spec), as was done for 01-03.
- **`/domain-modeling`** — ticket 04 introduces LLM-inferred `DomainEntity` nodes + `produces`/`consumes`/`transforms` edges; worth a modeling pass if the schema needs extending.
- **`/to-tickets`** — only if 04/05 need further decomposition before implementation (they are already ticketed, so likely unnecessary).
- **`/handoff`** — at the end of the next session, to continue the chain.
