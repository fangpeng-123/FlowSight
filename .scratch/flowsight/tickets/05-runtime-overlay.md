# 05 - Runtime data-flow overlay (runtime truth)

**What to build:** Capture a real runtime trace and overlay it on the skeleton so the user sees actual data flowing - real argument/return values, call counts, timings, and which edges actually fired. Driven by viztracer (the only tracer that reconstructs async chains), mapped onto skeleton Function nodes by file:line / f_code.

**Blocked by:** 02 (overlay renders on the dependency view). The actual-on-expected divergence comparison enriches once 03/04's LLM data_flow_role is available.

**Status:** ready-for-agent

- [ ] `flowsight trace <cmd>` wraps an entrypoint with viztracer to produce a trace; `--from <file.json>` ingests an existing trace
- [ ] Trace events map onto skeleton Function nodes by file:line / f_code
- [ ] Runtime `data_flow` edges carry real arg_values, return_values, call_count, timings, trace_id
- [ ] Dependency view overlays actual-on-expected; fired vs not-fired edges are distinguished/highlighted
- [ ] Async call chains are reconstructed correctly (viztracer)
- [ ] Overlay correlator is unit-tested with a checked-in fixture trace
- [ ] Expected-flow divergence comparison activates once 03/04 land (uses LLM data_flow_role as the expected baseline)
