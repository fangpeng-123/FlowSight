# 02 - Python analysis & tracing primitives

Type: research · Status: resolved · Blocked by: -

## Question

What primitives are available for (a) statically extracting a Python code graph and (b) runtime-tracing real data flow in Python?

Static: tree-sitter-python, stdlib `ast`, jedi, pyright/LSP, importlib. Runtime: `sys.settrace`, `sys.audit`, coverage.py internals, import hooks / monkey-patching, py-spy, viztracer, scalene. For each: what edges/data it captures, async/generator/C-extension limits, performance cost, maturity, license. Goal: a recommended stack for the static skeleton and the runtime overlay.

## Answer

Findings: `../research/python-primitives.md` (168 lines; claims probed on CPython 3.14. Web was blocked in the research env, so re-confirm version figures before pinning versions.)

**Static skeleton stack:** `ast` (primary - zero-dep, exact call-site/import/def inventory with line offsets to anchor runtime traces) + `importlib`/`pkgutil` (module/package boundaries, project vs site-packages) + `jedi` (lightweight call-site→def resolver; `pyright`/LSP as an optional precision upgrade behind a flag) + `tree-sitter` only if the UI needs incremental re-parse or comment/whitespace ranges.

**Runtime overlay stack:** `viztracer` (primary - every-call edges + arg/return values via instrumentation + first-class async per-task timelines; Chrome Trace JSON output) + `sys.monitoring` 3.12+ (low-overhead fallback for call/return + selective value capture via `frame.f_locals`) + `sys.audit` (executed-import + I/O provenance) + `py-spy`/`scalene` (production/long-running, C-ext visibility, no values) + selective import-hook/monkey-patch on sink/source functions (targeted, low-noise value capture).

**Called-out gaps:** only `viztracer` reconstructs logical async chains (`settrace`/`monitoring` break caller→callee across `await`; raw settrace on `asyncio.run` is very noisy). Only `py-spy`/`scalene` see into native C frames (`settrace`/`viztracer` see gaps; `setprofile` catches C-call boundaries only). Generators over-count under settrace - dedupe by `f_code` identity.

Feeds: 04 (core architecture - skeleton primitives), 06 (runtime overlay technique).
