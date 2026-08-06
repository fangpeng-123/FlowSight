# Python Primitives Survey for FlowSight

Goal: pick primitives for (a) a **static code-graph skeleton** (definitions, call sites, imports, type/resolution hints) and (b) a **runtime data-flow overlay** (real call edges, arg/return values, import events). Surveyed 2026-08; Python 3.14 used for probes.

Claims marked **[probed]** were verified with tiny scripts on CPython 3.14.2 in this environment. Others are from tool documentation/knowledge; web access was blocked in this environment, so version-specific figures should be re-confirmed against current docs before pinning versions.

---

## Part A — Static extraction primitives

### 1. stdlib `ast`
- **Edges/data captured**: Full syntactic tree. `Call` nodes (with `func` = `Name`/`Attribute`/etc. — the *call site* expression, **not** the resolved target), `Import`/`ImportFrom` (module + aliases), `FunctionDef`/`AsyncFunctionDef` (incl. decorators, args, defaults, *args/**kwargs), `ClassDef`, `Yield`/`YieldFrom`, `Await`, `Return`, comprehensions, assignments, attribute access. Line/col offsets on every node. **[probed]**: an async-def with `await`, a `yield`, two `Call`s, and three import forms all appear with correct node types and line numbers.
- **Resolution**: None. `helper(...)` and `client.get(...)` are recorded as expressions; you do not learn *which* `helper` is invoked. No types.
- **Async/generator/C-ext**: Full syntactic support (async-def, await, async-comprehension, yield-from all parse). No runtime/C-ext concept (it is static text).
- **Performance**: Negligible — parsing a file is microseconds-to-low-ms; `ast.walk` visitor over a tree is fast. No subprocess.
- **Maturity / License**: Shipped with CPython since forever. PSF license. 100% stable, but the node schema evolves across versions (e.g. docstring as `Constant`, pattern-matching nodes in 3.10+, type-parameter nodes in 3.12+).
- **Fit for FlowSight**: **Core skeleton builder.** Cheap, always available, gives exact call-site/import/def inventory with positions to anchor runtime traces against. Pair with a resolver (jedi/pyright) to turn call *sites* into call *edges*.

### 2. `tree-sitter-python`
- **Edges/data captured**: Concrete syntax tree (CST) with full byte ranges, *including comments and whitespace structure* that `ast` discards. Same syntactic categories as `ast` (calls, imports, defs, etc.) exposed as named nodes via a grammar. Incremental re-parse on edit.
- **Resolution**: None (purely syntactic, like `ast`).
- **Async/generator/C-ext**: Full syntactic support; grammar tracks Python evolution.
- **Performance**: Native C parser, very fast; incremental parsing makes it ideal for editor/live-update scenarios. Requires a binary wheel per platform.
- **Maturity / License**: MIT. High maturity; grammar maintained by the tree-sitter org, used by Neovim/Helix/GitHub code search.
- **Fit for FlowSight**: Strong alternative to `ast` if you need (a) comments/whitespace ranges or (b) incremental re-parsing for an interactive UI. If you only do one-shot batch extraction, `ast` is simpler and dependency-free. tree-sitter wins for the *interactive graph* UX.

### 3. `jedi`
- **Edges/data captured**: Static *semantic* analysis. `Script(...).get_references()`, `goto()`, `get_signatures()`, `get_call_signatures()`. Resolves a `Name`/`Attribute` call site to the definition it refers to (inference over imports, classes, assignments, decorators). Gives call *edges* (site -> def), find-references, completions. Partial type inference.
- **Resolution**: Yes — this is its core value over `ast`/tree-sitter. Handles many dynamic patterns (duck typing heuristics) but degrades on heavy metaprogramming / runtime-built symbols.
- **Async/generator/C-ext**: Understands async-def/generator syntax; does not execute C extensions (static). Cannot resolve calls that only exist at runtime (e.g. `getattr(obj, name)()`).
- **Performance**: Pure-Python-ish; reasonably fast for single-file/goto, but a full-project inference pass is slower than `ast`. No subprocess.
- **Maturity / License**: MIT. Very mature; powers IPython `%edit`, vim-jedi, and many editors. Maintained, but type-stub (PEP 561) world has shifted attention to pyright/LSP for heavy lifting.
- **Fit for FlowSight**: Good **lightweight resolver** to upgrade `ast` call-sites into call-edges without spawning an LSP server. Best for "good enough" resolution in a personal tool. Consider pyright if you need stronger typing.

### 4. `pyright` / LSP (pygls, pylsp)
- **Edges/data captured**: Pyright is a fast static type-checker (TypeScript impl) with full type inference. Exposes via LSP: `textDocument/callHierarchy` (incoming/outgoing call edges), `definition`, `references`, `typeDefinition`, hover types, diagnostics. Resolves call sites to defs **with type-aware precision** (generics, overloads, protocols).
- **Resolution**: Strongest available. Handles stubs (typeshed), PEP 695 type params, dataclasses, etc.
- **Async/generator/C-ext**: Static; understands async/generator types (`Coroutine`, `AsyncGenerator`); cannot see runtime-only symbols.
- **Performance**: Pyright itself is fast (incremental, in-memory). Running it as an LSP server (pygls/pylsp wrapper or pyright `--outputjson`) introduces a long-lived process; first analysis of a large repo is seconds, then incremental is cheap.
- **Maturity / License**: Pyright MIT (Microsoft). Very mature, actively developed. LSP layer (pygls) Apache-2.0; pylsp is community/LGPL-ish plugin ecosystem — check plugin licenses.
- **Fit for FlowSight**: **Heavyweight resolver.** Use if you want high-fidelity, type-aware call edges and can afford an LSP server process. For a personal tool, jedi may suffice; pyright is the upgrade path for precision. The LSP `callHierarchy` request maps almost directly onto FlowSight's static edge set.

### 5. `importlib` (stdlib)
- **Edges/data captured**: Module-discovery and import machinery. `importlib.util.find_spec()` resolves a module name to a file path; `importlib.metadata` enumerates installed packages/entry points/distribution deps; `pkgutil.walk_packages` walks an installed package tree. Captures **import/module edges** at the package level (which modules exist, where they live, what a distribution depends on), not function-level calls.
- **Resolution**: Resolves module names to files; does not resolve intra-module call targets.
- **Async/generator/C-ext**: N/A (metadata/discovery).
- **Performance**: Cheap for `find_spec`/`metadata`; `walk_packages` over a big tree imports submodules (can execute code) — prefer `pkgutil.iter_modules` with prefix to avoid execution where possible.
- **Maturity / License**: PSF stdlib. Rock solid.
- **Fit for FlowSight**: **Module/package inventory layer.** Use to map the project boundary (which files are project vs. site-packages), resolve `from x import y` module parts to paths, and detect 3rd-party vs. local modules for the graph's external-node policy.

---

## Part B — Runtime data-flow primitives

### 1. `sys.settrace`
- **Edges/data captured**: Per-thread callback for events `call`, `line`, `return`, `exception` on **Python** functions. **[probed]**: captures call edges (caller frame -> callee `f_code`), per-line execution, and return values (`arg` on `return`). Argument values are obtainable via `frame.f_locals` on the `call` event. For generators: a `call`+`return` pair fires **per resume**, and the yielded value appears as the `return` arg on intermediate yields (final `return` arg is `None`/StopIteration value). **[probed]**
- **C-extension limitation**: **Does not trace C builtins/methods at all** — `len()`, `list.append`, `sum()` produce no events. **[probed]** A call into a C extension looks like a gap (the Python caller's `line` event, then nothing until control returns). Use `sys.setprofile` if you need C-call edges.
- **Async limitation**: **[probed]** Traces coroutine frames, but the event loop's internals (`asyncio.run`, `__init__`, `_lazy_init`, `new_event_loop`, `Task.__step`, …) generate huge noise, and the caller->callee stack is **broken across `await`**: when a coroutine resumes, the Python call stack no longer contains the awaiting function (it resumes from the event loop's C machinery). Reconstructing "main awaited foo" requires correlating `Task`/coroutine identities manually.
- **Generator limitation**: Works, but a single generator produces N call/return pairs (one per `next()`); the logical "generator frame" is re-entered, so naive edge-counting over-counts. Distinguish via `frame.f_code` identity.
- **Performance**: **High overhead** — typical 5x–50x slowdown (per-line tracing is the most expensive). Memory grows with event volume.
- **Maturity / License**: PSF stdlib. Stable, but CPython 3.12+ deprecated some tracing interactions and PEP 669/`sys.monitoring` is the modern lower-overhead replacement for heavy tracing.
- **Fit for FlowSight**: **The value-capture workhorse** (args + returns), but wrap with `sys.monitoring` (3.12+) to cut overhead, and expect to write async/generator-aware glue.

### 1b. `sys.monitoring` (PEP 669, 3.12+) — note
- The modern, lower-overhead replacement for `settrace`/`setprofile`: per-event-type registration (CALL, PY_START, PY_RESUME, PY_RETURN, LINE, etc.), tool IDs, and per-code-object enable/disable. Same data dimensions as settrace (call/return/arg/locals) but **dramatically lower overhead** (designed so multiple tools don't each pay full trace cost). Same async/C-ext gaps as settrace (it is still Python-frame tracing). For a 3.12+ personal tool, **prefer `sys.monitoring` over raw `settrace`**.

### 2. `sys.setprofile`
- **Edges/data captured**: `call`/`return` for Python functions **plus `c_call`/`c_return`/`c_exception` for C builtins/methods**. **[probed]**: `len`, `list.append`, `sum` all emit `c_call`/`c_return`. Coarser than settrace (no per-line), so **lower overhead**. Good for a pure call-graph incl. C calls. Arg/return *values* not directly in the event (the `arg` for c_call is the C function object; for return it's the Python frame's return).
- **Limitations**: Same async caller-chain break as settrace; no per-line; c_call doesn't give you C-level args.
- **Performance**: Lower than settrace (no per-line events), but still measurable (often ~1.5x–3x depending on call density).
- **Maturity / License**: PSF stdlib.
- **Fit for FlowSight**: Use for a **lightweight call-edge layer incl. C calls** when you don't need arg values; combine with settrace/monitoring selectively for value capture.

### 3. `sys.audit` (`sys.addaudithook`)
- **Edges/data captured**: Security/lifecycle **events**, not general call edges. **[probed]** confirmed events: `import` (carries module name, path, sys.path, finders, path_hooks), `exec`, `compile`, `open`, `marshal.loads`, `os.listdir`, `object.__setattr__`, `sys._getframemodulename`. ~100+ audited events cover imports, file/socket I/O, code compilation, dynamic exec/eval, ctypes, etc.
- **Resolution**: Tells you *what was imported/opened/execed* with real argument values (e.g. the exact import name and resolved path) — excellent for **import edges and I/O data-flow**. Does **not** fire on ordinary function calls, so it is not a call-graph primitive.
- **Limitations**: No async/generator concept; hooks are global and cannot be removed (add-only). Some events fire from deep in C with minimal Python context.
- **Performance**: Designed to be cheap (lightweight hook list), but every audited operation pays a small tax; heavy hooks can still bite. Sandboxed/locked-down interpreters may restrict hooks.
- **Maturity / License**: PSF stdlib (3.8+). Stable.
- **Fit for FlowSight**: **Import-edge + I/O provenance overlay.** Pairs with static `importlib`/`ast` imports to record which imports *actually executed* and which files/sockets were touched at runtime — useful for "real data flow" into/out of the filesystem and across module boundaries.

### 4. `coverage.py` internals
- **Edges/data captured**: Line and branch (arc) coverage. Internally built on `sys.settrace` (Python tracer) with an arc-measurement algorithm that records `(prev_line, curr_line)` transitions → effectively a **per-file executed-control-flow graph** (which branches were taken). v7+ also has `sys.monitoring` support. Does **not** capture arg/return values or inter-function call edges by default.
- **API for reuse**: `coverage.CoverageData` gives per-file executed line numbers and arcs; the `Plugin`/`CTracer` API lets you hook measurement. You can ride its tracer rather than hand-rolling settrace.
- **Limitations**: Same as settrace (no C calls, async caller-chain break). Arc data is line-oriented, not expression/value-oriented.
- **Performance**: Optimized C tracer (`coverage.tracer`) when available; still a tracing tax (a few x). `sys.monitoring` backend reduces this on 3.12+.
- **Maturity / License**: Apache-2.0. Ned Batchelder; extremely mature, widely depended on.
- **Fit for FlowSight**: Reuse for **executed-branch/line overlay** (which static edges were actually exercised) rather than building arc measurement yourself. For arg/return values you still need your own tracer on top.

### 5. Import hooks / monkey-patching
- **Edges/data captured**: PEP 302/451 meta-path finders and loaders intercept **imports** (wrap a module on load). Monkey-patching wraps selected functions/methods/classes to log **calls, arguments, return values, exceptions, and even attribute access** — full data-flow capture *for wrapped symbols*. Can capture arg/return values precisely (you control the wrapper).
- **Resolution**: Only what you wrap; fully general (works for runtime-built/dynamic symbols that static analysis can't see). But you must *know what to wrap* (from static inventory or import hooks).
- **Limitations**: C extensions can be wrapped only at their Python-visible boundary (you can wrap the imported function object, but not internals). Generators/async fine if you wrap the coroutine/generator factory and the resulting iterator/coroutine. Invasive — can change program behavior, break pickling, hide stack frames from other tracers, or deadlock if wrappers re-enter.
- **Performance**: Near-zero for un-wrapped code; wrapped calls pay the wrapper cost (usually small). Selective wrapping keeps overhead controllable.
- **Maturity / License**: PSF stdlib (importlib hooks) + your own code.
- **Fit for FlowSight**: **Targeted value-flow instrumentation** — wrap the handful of "sink/source" functions (DB calls, HTTP, file I/O, key business logic) identified by the static graph to capture real arg/return values with low overhead. Complements sampling profilers (which can't see values).

### 6. `py-spy`
- **Edges/data captured**: **Sampling** profiler. Captures call stacks at a configurable sample rate (default ~100 Hz, up to kHz), producing flame-graph / speedscope output. Aggregates **call edges present on the stack** (caller->callee by frame co_name) and time-in-function. **No arg/return values** (sampling cannot inspect per-call values reliably).
- **C-extension**: **Yes** — reads native stack frames, so C extension and even non-Python frames appear (subject to symbols being available). This is a key advantage over settrace-family tools.
- **Async**: Shows async stacks but a sampling profiler sees whatever is on the (real, OS) stack at sample time — suspended coroutines are not on the stack, so you see the event loop running (or idle) rather than "logical" async call chains. May misattribute time to `Task.__step`/loop internals.
- **Limitations**: Statistical — misses calls shorter than the sampling interval; cannot give exact call counts or per-call values. On Windows uses process-memory reading (no signals); attach to running processes supported.
- **Performance**: **Low** — designed for production; ~1-5% overhead typical at default rates, no code changes, no restart needed (can `py-spy record --pid`).
- **Maturity / License**: MIT. Ben Frederickson; very mature, widely used for production profiling. Rust core.
- **Fit for FlowSight**: **Production-grade hot-path / call-frequency overlay with C-ext visibility and near-zero overhead.** Best when you want real call edges *without* instrumenting or when targeting long-running processes. Cannot replace value capture.

### 7. `viztracer`
- **Edges/data captured**: **Deterministic tracing** profiler (every event, not sampling). Captures function call + return with wall-clock timestamps and durations, thread/coroutine timelines. **Can capture arg/return values** via `viztracer.register_func("module.func")` and the "extra info" mechanism (`vinstrument` / `VizTracer.log_event` / `log_instant`/`log_variable`) — you can attach variable values, function args, and return values to events. Outputs Chrome Trace Event JSON (viewable in Perfetto/chrome://tracing) + flame graph.
- **C-extension**: Built on `sys.settrace`/`setprofile` + AST instrumentation, so **C functions are not traced as Python calls** unless wrapped; native calls appear as gaps. (It does not read native stacks like py-spy.)
- **Async**: **First-class async support** — traces coroutines/threads with per-task timelines and can attribute async causality (it tracks `Task` creation and `await` transitions, so it reconstructs logical async chains far better than raw settrace). Generators traced per-resume.
- **Limitations**: Deterministic tracing → higher overhead than sampling; very large traces for long runs (it has a circular-buffer / max-stack-depth / min-duration dump options to bound this).
- **Performance**: Moderate-to-high (tracing every call). Configurable (filter by module, depth, duration) to reduce cost. Slower than py-spy, faster-feeling than full settrace+value-logging because it's optimized C-ish code, but still a tracer.
- **Maturity / License**: Apache-2.0. Tian Gao (originally Broad Institute/DOE); mature, actively maintained, good docs.
- **Fit for FlowSight**: **Best-fit runtime overlay for data-flow + async.** Gives timed call edges, per-task async timelines, *and* arg/return values via instrumentation — the closest single tool to "real data-flow traces" with async/generator awareness. Overhead is the tradeoff; use filtering to keep it bounded.

### 8. `scalene`
- **Edges/data captured**: **Sampling** profiler, line-level, with **CPU + memory (allocations/copies) + GPU** attribution per line of Python (and per C line where symbols allow). Captures which lines ran and how much CPU/memory they cost; does **not** capture arg/return values (sampling-based). Reports memory allocations per line — useful indirect data-flow signal (where objects are born).
- **C-extension**: Yes — samples native stacks, so C extensions are attributed (better than pure-Python tracers).
- **Async**: Sampling-based, same caveat as py-spy: sees real OS stacks, suspended coroutines invisible; async chains not natively reconstructed.
- **Limitations**: Statistical (misses sub-sample work); no per-call values; memory tracking adds some overhead and can be noisy on short runs.
- **Performance**: Low overhead (sampling + signal-based in C extension); designed to be usable in production-ish settings, though memory tracking costs more than CPU-only.
- **Maturity / License**: Apache-2.0. Emery Berger (UMass); mature, actively maintained.
- **Fit for FlowSight**: **Memory/allocation provenance overlay** — complements py-spy by showing *where data objects are created/copied*, a strong data-flow signal, at line resolution with C-ext support. Not a value-capture tool.

---

## Cross-cutting comparison

| Primitive | Call edges | Arg values | Return values | Imports | Async | Generators | C-ext | Overhead | License |
|---|---|---|---|---|---|---|---|---|---|
| `ast` | sites only (no resolve) | no | no | yes (syntactic) | syntax yes | syntax yes | n/a | negligible | PSF |
| `tree-sitter-python` | sites only | no | no | yes (syntactic) | syntax yes | syntax yes | n/a | very low | MIT |
| `jedi` | **resolved** edges | no | no | resolved | static yes | static yes | static | low-medium | MIT |
| `pyright/LSP` | **resolved** + types | no | no | resolved | static yes | static yes | static | medium (server) | MIT |
| `importlib` | module-level | no | no | **yes** (executed) | n/a | n/a | n/a | low | PSF |
| `sys.settrace` | yes (Py) | yes (f_locals) | yes | indirect | weak/broken | yes (per-resume) | **no** | high | PSF |
| `sys.monitoring` | yes (Py) | yes | yes | indirect | weak/broken | yes | **no** | low-medium | PSF |
| `sys.setprofile` | yes (Py+C) | limited | limited | indirect | weak/broken | yes | **yes** | medium | PSF |
| `sys.audit` | no | yes (event args) | no | **yes** (executed) | n/a | n/a | partial | low | PSF |
| `coverage.py` | arcs/lines | no | no | indirect | weak | yes | **no** | low-medium | Apache-2.0 |
| import hooks / monkey-patch | wrapped only | **yes** | **yes** | **yes** | fine | fine | boundary-only | low (selective) | PSF (+yours) |
| `py-spy` | yes (sampled, Py+C) | no | no | no | weak (sampling) | weak | **yes** | **very low** | MIT |
| `viztracer` | yes (every call) | **yes** (instr) | **yes** (instr) | indirect | **strong** (per-task) | yes | **no** | medium-high | Apache-2.0 |
| `scalene` | lines + CPU/mem | no | no | no | weak | weak | **yes** | low | Apache-2.0 |

"weak/broken" for async = the Python caller->callee stack does not span `await` without extra correlation.

---

## Recommended stack

### Static skeleton
1. **`ast` as the primary skeleton builder** — always-available, zero-dep, exact call-site/import/def inventory with line offsets to anchor runtime traces. Use a visitor to emit nodes: `FunctionDef`/`AsyncFunctionDef`/`ClassDef` (defs), `Call` (call sites with site-id + position), `Import`/`ImportFrom` (imports), `Yield`/`Await` (async/gen markers).
2. **`importlib` + `pkgutil` for module/package boundaries** — resolve `from x import y` module parts to paths, separate project vs. site-packages, drive which files to parse.
3. **`jedi` as the default call-site resolver** (call site -> def) — lightweight, in-process, "good enough" for a personal tool to upgrade `ast` call-sites into true call-edges. Keep **pyright/LSP** as an optional upgrade path for users who want type-aware precision (PEP 695, overloads, protocols); expose it behind a flag rather than depending on a long-lived server by default.
4. **`tree-sitter-python` only if** the FlowSight UI needs incremental re-parsing or comment/whitespace ranges; otherwise `ast` suffices for batch extraction.

### Runtime overlay
1. **`viztracer` as the primary data-flow tracer** — the only single tool that combines *every-call* edges, *arg/return values* (via instrumentation), and **first-class async per-task timelines**. Output Chrome Trace JSON; map its events onto the static skeleton by `co_filename`+`co_firstlineno`+`co_name`.
2. **`sys.monitoring` (3.12+) as the low-overhead fallback / always-on layer** — when viztracer's full tracing is too costly, use `sys.monitoring` for call/return edges + selective value capture via `frame.f_locals` on PY_START. (On 3.11 and below, fall back to `sys.settrace`/`setprofile`.) This is the path for capturing arg/return values without viztracer's full event volume.
3. **`sys.audit` for import + I/O provenance** — record which imports *actually executed* and which files/sockets were touched, correlating to the static import edges. Cheap, add-only, complements the call tracer.
4. **`py-spy` + `scalene` for production/long-running targets** where instrumentation isn't acceptable — py-spy for sampled call edges *with C-extension visibility* (fills the C-call gap that settrace/viztracer leave), scalene for line-level memory/allocation provenance (where data objects are born). Neither gives values; use them to enrich frequency/hot-path and allocation-flow, not to replace value capture.
5. **Selective import-hook / monkey-patch wrappers for sinks/sources** — wrap the small set of I/O / DB / HTTP / key business functions identified by the static graph to capture precise arg/return values at low overhead. This is the targeted, low-noise complement to viztracer's broad tracing.

### Called-out async / generator gaps
- **Async**: `sys.settrace`/`monitoring`/`setprofile` all break the caller->callee chain across `await` (coroutines resume from the event loop's C machinery, so the awaiting frame is not on the Python stack). **[probed]** Raw settrace on `asyncio.run` is also extremely noisy (event-loop internals dominate). **viztracer is the only recommended primitive that reconstructs logical async chains** (it tracks `Task` creation + `await` transitions). For py-spy/scalene, suspended coroutines are invisible (sampling sees only the running event loop) — async attribution will be weak.
- **Generators**: settrace/monitoring emit a call+return pair **per resume** and surface the yielded value as the `return` arg **[probed]**; naive edge-counting over-counts, so dedupe by `f_code` identity and model a generator as a re-entrant frame rather than N distinct calls. viztracer handles this; sampling profilers (py-spy/scalene) under-attribute generator cost.
- **C extensions**: settrace/monitoring/viztracer/coverage see **no** C-internal calls (only gaps); `sys.setprofile` captures C-call *boundaries* (c_call/c_return) but not C-internal args; **py-spy and scalene are the only primitives that see into native C frames** (via stack sampling). For data-flow across a C extension boundary, wrap the Python-visible entry point with a monkey-patch.
