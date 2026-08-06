# 03 - LLM enrichment + trust marking + caching (meaning layer)

**What to build:** Inject LLM-derived meaning into the skeleton - eager module purpose at index, lazy per-function drill-down (contract / data-flow role / risk) on click - shown in the side panel, with parser-trusted structure visually distinct from LLM-advisory annotations, and enrichment cached per code-hash so only changed functions re-enrich.

**Blocked by:** 02 (needs the rendered graph + node selection to trigger drill-down).

**Status:** ready-for-agent

- [ ] At index time every module has an eager one-line `purpose`
- [ ] Clicking a function node triggers lazy LLM enrichment: purpose + contract{inputs, outputs, errors, boundaries} + data_flow_role + risk, shown in the side panel
- [ ] LLM-sourced attributes (advisory) are visually distinct from parser-sourced (trusted)
- [ ] Enrichment is cached per function code-hash; a code change invalidates only that entry, re-enriched lazily on next view
- [ ] LLM is behind an interface and stubbable: unit tests assert enrichment is keyed/attached/cached/invalidated, never asserting LLM content
