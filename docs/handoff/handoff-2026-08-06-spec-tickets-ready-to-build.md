# Handoff: FlowSight — spec & tickets ready to build

**Date:** 2026-08-06 · **Repo:** https://github.com/fangpeng-123/FlowSight (branch `main`, clean, all pushed)

## Session outcome in one paragraph

FlowSight moved from a verified 3D prototype to a build-ready state. The three prototype bugs (theme background, missing legend, unclear data flow) were fixed and **verified by the user** — root cause was a nonexistent `onNodeDblClick` method in 3d-force-graph v1.80 that broke the constructor chain (see prior handoff `handoff-2026-08-06-prototype-v5c-onnodedblclick-chain-fix.md`). Then `/to-spec` produced a build-ready MVP spec, and `/to-tickets` broke it into 5 tracer-bullet tickets. The project is now ready to start building ticket 01.

## Current state

- **Repo:** 3 commits on `main`, all pushed to GitHub:
  - `0c43108` init (prototype + research + issues + handoffs)
  - `feea989` MVP spec + map registration
  - `5c03cea` /to-tickets 5 tracer-bullet tickets
- **Prototype:** `.scratch/flowsight/prototype/index.html` — verified working, 3d-force-graph v1.80. The reference realization of decision 07.
- **Spec:** `docs/spec/flowsight-mvp-spec.md` — `ready-for-agent`. Synthesizes decisions 02–08 + the verified prototype + landscape survey.
- **Tickets:** `.scratch/flowsight/tickets/01`–`05` — `ready-for-agent`. Frontier = **01 (skeleton extraction, no blockers)**.
- **Tracker:** `.scratch/flowsight/map.md` — has `## Build spec (ready-for-agent)` and `## Build tickets (ready-for-agent)` sections listing the dependency graph and frontier.
- **Memory:** `prototype-verified-dev-phase.md` records the prototype-verified → dev-phase transition.

## Decisions locked this session (via /to-spec — do not re-litigate)

Recorded in `map.md` and the spec; referenced here only as pointers:
- **03 renderer** → 3d-force-graph (supersedes Cytoscape for the MVP; user preference + verified prototype). Cytoscape's "framework-agnostic graph layer" advice retained as a renderer-agnostic data adapter.
- **06 runtime overlay** → viztracer actual-on-expected; `flowsight trace <cmd>` or `--from <file.json>`; mapped by file:line / `f_code`.
- **08 medium** → local web app (browser); graph layer host-agnostic for a future webview.

## Operational facts a fresh agent MUST know (not in any project artifact)

These are environment/harness facts, not in the repo — read them:

1. **Classifier intermittently unavailable.** The bash/Write safety classifier (model `glm-5.2`) goes through periods of "temporarily unavailable." When down, it blocks **write/network** operations (`git add`/`commit`/`push`, `mkdir`, bash redirects, `Write` tool). **Read-only** ops (`Read`, `Grep`, `Glob`, read-only `git status`, `gh api --jq` without redirect) keep working. Workaround: ask the user to run the command with a `!` prefix (e.g. `!cd F:/FlowSight && git push origin main`) — user-initiated commands bypass the classifier entirely. Retry also sometimes works once the classifier recovers.
2. **Git push needs V2Ray.** Push to GitHub must go through V2Ray HTTP proxy `http://127.0.0.1:10808` (git is globally configured with `http.proxy`/`https.proxy`). Before pushing, confirm V2Ray is running. `Recv failure: Connection was reset` or `Failed to connect to github.com port 443` = V2Ray not started. `gh` CLI API calls succeeding does NOT imply `git push` works — don't infer one from the other.
3. **`/to-spec` and `/to-tickets` cannot be invoked by the agent** — both have `disable-model-invocation: true`. The user must type `/<name>` to run them. Installed globally at `C:\Users\Administrator\.claude\skills\to-spec/` and `…/to-tickets/`.
4. **No CodeGraph.** FlowSight has no `.codegraph/` directory — skip CodeGraph entirely (per global CLAUDE.md). Note: the FlowSight spec deliberately does NOT reuse CodeGraph for the skeleton (decision 04 builds on `ast`+`jedi` directly); CodeGraph is reference prior art only.
5. **No native vision.** The session model has no image understanding. For images, use the vision skill script: `node "C:/Users/Administrator/.claude/skills/vision/vision.js" "<path>" "<question>"`.
6. **Tracker convention.** `issues/` = wayfinder **decision** tickets (01–08, mostly resolved). `tickets/` = **build** slices (01–05, ready-for-agent). Both number from 01 in their own sequence — don't confuse the two.

## Next steps

1. **Claim and build ticket 01** (`.scratch/flowsight/tickets/01-skeleton.md`) — the data spine, no blockers. Implement against its acceptance criteria + the spec's schema (05) + architecture (04).
2. Then **02** (serve + 3D render), which adapts the verified prototype to consume real served graph JSON.
3. Dependency graph: `01 -> 02 -> 03 -> 04`; `02 -> 05` (05 runs parallel to 03/04). Work the frontier (any ticket whose blockers are done).

## Suggested skills

- **`/handoff`** — to write the next handoff when this context fills.
- **`/to-tickets`** — if tickets need re-splitting/merging during build (user must invoke).
- **`/to-spec`** — if a sub-area needs a sharper spec (user must invoke).
- **`/prototype`** — for "how should it look" questions (per `map.md` Notes).
- **`/grilling` + `/domain-modeling`** — default for architectural decisions (per `map.md` Notes).
- **`/research`** — for outside-codebase facts (per `map.md` Notes).
- **vision skill** — for any image (screenshots of the running graph, etc.).

## Key paths

| Artifact | Path |
|---|---|
| MVP spec | `docs/spec/flowsight-mvp-spec.md` |
| Build tickets | `.scratch/flowsight/tickets/01`–`05` |
| Decision tickets | `.scratch/flowsight/issues/01`–`08` |
| Tracker map | `.scratch/flowsight/map.md` |
| Prototype | `.scratch/flowsight/prototype/index.html` |
| Research | `.scratch/flowsight/research/{landscape,python-primitives,graph-viz}.md` |
| Prior handoffs | `docs/handoff/handoff-2026-08-06-prototype-v{3,4,5c…}.md` |
