# 04 - Domain entities + four views + search (facets)

**What to build:** Surface the LLM-inferred domain model and the four facet views. DomainEntity nodes and produces/consumes/transforms edges are inferred from function inputs/outputs; four view tabs filter the graph to each schema subset; risks are ranked; cross-facet search jumps to any node.

**Blocked by:** 03 (needs enrichment producing contracts/risks/domain entities).

**Status:** implemented (committed in d6d078a alongside concurrent ticket-05 work)

- [x] LLM infers DomainEntity nodes + produces/consumes/transforms edges from function inputs/outputs (lazy/progressive)
- [x] Four view tabs (dependency / data-structures / contracts / risk) each filter the graph to their schema subset
- [x] Risk view ranks items by severity
- [x] Search covers functions/structs/risks and jumps to the selected node
- [x] Data-structures view shows the domain data pipeline (e.g. AudioChunk -> Transcript -> LLMMessage -> TTSAudio)
