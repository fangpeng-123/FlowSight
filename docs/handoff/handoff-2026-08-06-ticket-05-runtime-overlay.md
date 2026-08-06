# Handoff — Ticket 05: Runtime data-flow overlay

**Date:** 2026-08-06
**Branch:** `main` (committed on top of `a1efa41` tickets 01-03)
**Status:** implemented, full suite green (60 Python + 22 JS), `/code-review` run + findings addressed.

> **Note on scope:** this commit also lands **ticket 04 (domain entities)**, which was
> developed concurrently in the same working tree and which ticket 05 builds on (the
> divergence baseline uses 04's `produces`/`consumes`/`transforms` + 03's
> `data_flow_role`; `adapter.js`/`app.py` carry both 04 and 05 changes in shared files).
> They could not be cleanly split across the mixed files, so they ship together.

---

## What ticket 05 delivers

A real runtime trace (viztracer) overlaid on the parser skeleton, so the user sees
**actual** data flowing — real arg/return values, call counts, timings, and which
edges actually fired — as a third trust layer (`origin=runtime`) on top of the
trusted parser skeleton and the advisory LLM layer.

### Checklist (`.scratch/flowsight/tickets/05-runtime-overlay.md`)
- [x] `flowsight trace <cmd>` wraps an entrypoint with viztracer; `--from <file.json>` ingests an existing trace
- [x] Trace events map onto skeleton Function nodes by file:def_line (= f_code identity: `co_filename` + `co_firstlineno`)
- [x] Runtime `data_flow` edges carry real `arg_values`, `return_values`, `call_count`, timings, `trace_id`
- [x] Dependency view overlays actual-on-expected; fired vs not-fired distinguished (color + width)
- [x] Async call chains reconstructed per (pid,tid) from event nesting (X by ts/dur, B/E by stack)
- [x] Overlay correlator unit-tested with a checked-in fixture trace (`tests/fixtures/trace.json`)
- [x] Expected-flow divergence comparison activates on 03/04 (`data_flow_role` baseline + produces/consumes/transforms)

---

## Files

**New (ticket 05):**
- `src/flowsight/overlay/__init__.py` — public API exports.
- `src/flowsight/overlay/correlator.py` — **the unit-tested seam (spec Seam 2).** Pure transform: viztracer Chrome Trace JSON + skeleton → runtime `data_flow` edges + per-node stats + actual-on-expected divergence. Never imports viztracer.
  - `correlate(doc, trace, *, project_root, trace_id)` — pure, no mutation.
  - `apply_overlay(doc, result)` — mutates: appends `data_flow` edges (`origin=runtime`), tags `calls`/`references` edges with `attrs["runtime"]={fired,call_count}`, writes `node.runtime` + `attrs["runtime_fired"]`.
  - Mapping: viztracer embeds `"<qualname> (<abs_path>:<def_line>)"` in each FEE event's `name`; def_line = `co_firstlineno` = the skeleton's `location.line`. Caller→callee reconstructed per (pid,tid); X nests by ts/dur, B/E by stack (mixed case fixed + tested).
  - Divergence: `not_fired` (static calls/references that didn't fire), `unexpected` (observed pairs with no static counterpart), `role` (cold data-path participant / hot "none").
- `src/flowsight/overlay/trace.py` — `run_trace` (viztracer subprocess, module/script mode), `load_trace`, `ingest_trace` (validate + stage), `overlay_graph_dict` (extract+correlate+apply+serialize). viztracer imported lazily.
- `tests/test_overlay.py` — 16 tests (fixture correlation, timings/values, divergence fired/not-fired, purity, apply_overlay, caller reconstruction, relativize, unmapped skip, unexpected edge, async separate-thread, mixed B/E+X, role divergence cold/hot, value capping).
- `tests/fixtures/trace.json` — checked-in viztracer-format trace of `voice_agent.run()` with `is_utterance_end=False`.

**Modified (ticket 05):**
- `src/flowsight/cli.py` — `trace` subcommand: `cmd` (REMAINDER, use `--` before `-m`), `--from`, `--out`, `--project`, `--overlay-out`, `--log-args`, `--max-stack-depth`; `serve --trace`.
- `src/flowsight/server/app.py` — `GraphState(trace_path=...)` correlates+applies overlay in `_build`; `/api/divergence` endpoint; `serve(..., trace_path=None)`.
- `src/flowsight/web/adapter.js` — `hasRuntime`, `linkRuntime`, `isUnexpectedFlow`; `linkColor`/`linkWidth` for data_flow (expected=flow / unexpected=rose) and calls/references (fired=normal / not-fired=muted+thin). Backward-compatible (no runtime attr = normal). Theme colors `unexpected`/`notFired`.
- `src/flowsight/web/app.js` — runtime card in the function panel (call_count, avg/min/max/total timings, sampled arg/return values); trace-active badge (fetches `/api/divergence`); `syncLegendVars` adds `--c-flow`/`--c-notfired`/`--c-unexpected`.
- `src/flowsight/web/index.html` — trace badge in panel head; legend entries (运行时数据流 / 未触发 / 异常调用).
- `src/flowsight/web/style.css` — line-swatch `.ln`, `.trace-badge` styles.
- `tests/test_adapter.mjs` — 4 new tests (hasRuntime, data_flow expected/unexpected color, calls fired/not-fired/untraced, buildRenderModel carries runtime attrs). 22 total.

**Ticket 04 (bundled, concurrent):** `src/flowsight/enrich/attacher.py` (`attach_entities`), `src/flowsight/server/enrich_api.py` (`/api/enrich` entity deltas, `/api/enrich-all`), `tests/test_entities.py` (7 tests), plus the 04 portions of `app.py`/`adapter.js`/`test_adapter.mjs`.

---

## How to run

```bash
# 1. Capture a live trace and overlay it on a project, then serve:
flowsight trace --log-args --project <project> --out .flowsight/trace.json -- <entrypoint>
flowsight serve <project> --trace .flowsight/trace.json

# 2. Or ingest an existing trace:
flowsight trace --from existing.json --project <project> --overlay-out graph-overlay.json

# 3. CLI correlation only (no server):
flowsight trace --from existing.json --project <project> --overlay-out out.json
```

`--log-args` is **off by default** (privacy): without it, `data_flow` edges carry call_count/timings/trace_id but empty `arg_values`/`return_values`.

---

## Validation

- **Live end-to-end** (`flowsight trace --log-args --project <tmp> -- <target.py>`): `outer(3)` → printed `6`; correlated `outer->inner` `data_flow` edge with `call_count=3`, `expected=True`, `arg_values=['x=0','x=1','x=2']`; per-node `inner cc=3 ret=['1','2','3']`, `outer cc=1 ret=['6']`.
- **Ingest end-to-end** (`--from tests/fixtures/trace.json --project tests/fixtures/voice_agent`): 4 runtime `data_flow` edges, 5 runtime nodes with captured args/timings.
- **Suite:** 60 Python + 22 JS green; `compileall` clean.

---

## Known limitations / deferred

- Cross-thread async tasks (e.g. `run_in_executor` callbacks) reconstruct as independent roots per (pid,tid). Same-thread `await` nests correctly. True cross-task causal linking is out of MVP scope.
- `NodeRuntime`/`EdgeRuntime` share a field shape (deferred refactor — judgement call, not worth regression risk).
- A `references` edge to a CLASS is marked fired if any method/constructor of the class ran (by design; enshrined in test).
- `/api/enrich-all` route is matched before `/api/enrich` via `startswith` (concurrent ticket-04 routing; currently correct, flagged as fragile).

## Next ticket
Ticket 05 was the last MVP tracer-bullet ticket. Suggested follow-ups: the deferred refactors above; cross-task async linking; surfacing the divergence report as a dedicated panel (currently a badge + `/api/divergence`).
