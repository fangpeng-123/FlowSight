# 05 - Graph schema & views

Type: grilling · Status: resolved · Blocked by: 04 (resolved)

## Question

What are FlowSight's graph nodes, edges, and layers? The user asked for four views: core data structures (entities + relations), interface contracts (I/O, error codes, boundaries), dependency graph (call direction + data flow), and risk list (pitfalls + avoidance). Define the schema: node types, edge types, and how the four views map onto them.

## Answer

**Decision: the FlowSight graph schema, with every attribute tagged by source - parser=trusted / LLM=advisory / runtime=actual.**

### Node types
- `Module` (parser) - file/package.
- `Function` (parser, incl. async) - the primary unit.
- `Class` (parser).
- `External` (parser) - 3rd-party symbol (jedi resolves to site-packages).
- `DomainEntity` (LLM, advisory) - inferred domain entity (e.g. AudioChunk, Transcript, LLMMessage) - the user's "关键实体".

### Edge types
- `calls` (parser, trusted) - Function -> Function, resolved by jedi.
- `imports` (parser, trusted) - Module -> Module/symbol.
- `contains` / `defined_in` (parser, trusted) - Function/Class -> Module; Method -> Class.
- `references` (parser, trusted) - Function -> Class/External (uses a type).
- `produces` / `consumes` (LLM, advisory) - Function -> DomainEntity.
- `transforms` (LLM, advisory) - DomainEntity -> DomainEntity via a Function (e.g. AudioChunk --ASR--> Transcript).
- `data_flow` (runtime, actual) - Function -> Function, carrying real arg values / call counts / timings (viztracer).

### Attributes by source
- **parser (trusted):** signature, location (file:line), args, decorators, is_async.
- **LLM (advisory):**
  - `purpose` (one-line)
  - `contract` = { inputs, outputs, errors (raised exceptions + error codes), boundaries (preconditions, postconditions, side-effects) } - matches "输入输出、错误码、边界约定"
  - `data_flow_role` (what data flows in/out, what it transforms)
  - `risk` = { category, severity, description (the pitfall), avoidance (the strategy) } - matches "坑点和规避策略"
- **runtime (actual):** call_count, arg_values, return_values, timings, trace_id.

### The four views = data subsets
1. **Dependency view** - `calls` + `imports` + `contains` edges; Module/Function/Class/External nodes. (parser, trusted) + runtime `data_flow` overlay (actual-on-expected).
2. **Data-structures view** - `DomainEntity` nodes + `produces`/`consumes`/`transforms` edges. (LLM, advisory) - the inferred domain data model.
3. **Contracts view** - `Function` nodes + `contract` attributes. (LLM, advisory)
4. **Risk view** - nodes carrying `risk` + an aggregate ranked list. (LLM, advisory)

### Enrichment scope (from 04)
- Module-level: `purpose` one-liner (eager).
- Function-level: `purpose` + `contract` + `data_flow_role` + `risk` (lazy, on drill-down).
- `DomainEntity` inference: LLM infers entities + transforms from function inputs/outputs across the codebase (lazy/progressive).

### Trust marking
Parser-sourced nodes/edges render as solid/trusted; LLM-sourced (DomainEntity, contract, risk, data_flow_role) render distinctly (e.g. dashed/italic) so the user knows structural truth vs model interpretation. Exact visual encoding is ticket 07.

**Feeds:** 07 (viz IA - now unblocked: render this schema with Cytoscape compound + expand-collapse; encode trust via visual style). 06 takes the runtime `data_flow` edge definition.
