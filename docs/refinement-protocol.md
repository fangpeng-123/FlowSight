# Module Deep-Read Refinement Protocol

FlowSight is the local request/status host. It does not start an Agent. The
Agent monitors newline-delimited JSON events and treats the filesystem job as
the source of truth.

## Browser API

- `POST /api/refinements` with `{"subject_id":"flowsight/server"}` creates or
  reuses a request and returns HTTP 202 with its current status. An optional
  `critical_path_extensions` string map can name evidenced continuation nodes
  and explain why each extra hop is needed.
- `GET /api/refinements/<job-id>` returns the durable status.
- `DELETE /api/refinements/<job-id>` cancels only a pending job.

An unclaimed job is reported as `pending`, stage `waiting_for_agent`, display
`Waiting for Agent`. Existing graph, divergence, enrichment, and reindex routes
remain independent.

## Durable layout

```text
.flowsight/refinements/jobs/<job-id>/
  request.json     immutable request, dossier, fingerprint, source scope
  status.json      mutable state presented to the browser
  result.json      Agent result metadata
  staged/final Agent outputs before acceptance
.flowsight/refinements/current/<subject-hash>/
  specification.json
  artifact.html    atomically replaced current artifact
  reverse-id-map.json
  delivery-receipt.json
```

The dossier contains the selected subject, owned file scope and hashes,
internal graph facts, bounded cross-subject facts, signatures, contracts,
risks, runtime evidence, locations, and origin tags. It contains no source
text. Contract version 4 preserves the exact requested `critical_path_extensions`
map, including extensions omitted by display budgets, for freshness replay.
It includes `source_scope.external_files`,
`relationships.external_context`, and the context policy/selection/overflow
summary. It also carries a bounded `nodes.critical_path_candidates` allowance
so the Agent can choose an evidenced second hop after claiming the immutable
request. Existing `nodes.boundary` and `relationships.boundary` remain the
compatibility names for selected one-hop context.

FlowSight commits `request.json` and `status.json` before emitting one compact
`refinement.requested` JSON line. The event contains only the event/job/subject/
project identifiers plus project-relative request and expected-result paths.
An Agent must scan existing pending jobs before relying on new events.

## Agent consumption and Archify delivery

The monitoring Agent authors exactly one `diagram_type: "architecture"` JSON
document plus a reverse map from Archify component IDs to FlowSight node IDs.
It can then consume the oldest durable request with:

```text
flowsight refine <project> --once \
  --spec <architecture.json> \
  --reverse-map <reverse-id-map.json> \
  --archify-root <archify-package>
```

This command is an Agent-side adapter; `flowsight serve` never starts or hosts
an Agent. Claiming uses an exclusive project-local active-claim file, so
replayed events and separate `JobStore` instances cannot process two jobs at
once. The reusable `RefinementAgent` API supports the initial candidate plus at
most two focused repairs. The file-based CLI performs one frozen candidate per
invocation, allowing the external Agent to revise its source before retrying.

All store state transitions, including browser cancellation and Agent claiming,
share an OS-backed project-local transaction lock. The OS releases that lock
when a process exits. Active claims record the local PID and process creation
identity; a later pending scan marks interrupted work failed and releases its
claim only after verifying that the owning process exited or its PID was reused.
Live or inaccessible owners are never evicted by elapsed time. Legacy claims
without process identity cannot be recovered automatically: after confirming the
old Agent stopped, an operator can mark that job failed with `JobStore.fail`.

Before Archify runs, FlowSight rejects any component without a reverse mapping
to a dossier node and any connection without parser- or runtime-origin edge
evidence. Runtime guided views are rejected when the dossier has no observed
runtime facts. Archify is invoked only as `deliver architecture ... --quality
showcase --json`; no diagram type is auto-selected.

Successful publication writes the checked specification, self-contained HTML,
reverse map, identity-bound receipt, and `result.json` through staging files,
with result metadata committed last. The receipt retains Archify's exact SHA,
byte-count, and validation claims under `archify_delivery`.

## Bounded cross-module context

Only direct incoming or outgoing relationships with parser/runtime provenance
are eligible by default. An optional critical-path extension must name an
existing node, carry a non-empty justification, and connect one evidenced hop
at a time to the current frontier. Disconnected suggestions and LLM-created
topology are rejected.

The default primary budget is two external reading subjects and six external
nodes. Subjects with more direct evidence rank first, runtime-observed evidence
breaks ties, and slots are distributed round-robin across the chosen subjects.
Anything outside either budget becomes a truthful aggregate grouped by owner,
with node type, direction, origin, relationship count, and omitted count. Only
files backing selected primary context enter `source_scope.external_files` and
the dossier fingerprint.

Every selected context node retains its exact primary owner, parser signature,
source location, evidence origin, hop, direction, and any critical-path
justification. The Agent delivery gate requires context components to use the
Archify `external` visual type, display owner and location, retain exact code
identifiers, and sit in owner-labelled external boundaries separate from the
selected subject. Runtime edges additionally require an observed label and
emphasis styling; a runtime view is still forbidden without runtime evidence.
If the dossier contains overflow, an owner-and-count aggregate must appear in
the artifact cards. Internal primary components are curated to 8–18 when the
subject contains at least eight candidates; omitted helpers are represented by
a visible exact count and category aggregate. Explanatory responsibility,
contract, and risk cards must be visibly marked as LLM advice.

## Result acceptance

The state path is `pending → claimed → generating → validating → ready`, with
`failed` and `cancelled` as explicit non-ready states. Diagnostics are bounded
to 1000 characters.

FlowSight registers a result only while the job is validating and only when the
request, result, and delivery receipt match its job ID, subject ID, and input
fingerprint. It independently verifies the Archify command/type, zero validation
findings, exact specification/artifact SHA-256 and byte counts, Architecture
component reverse mappings, and parser/runtime evidence for every connection
before promotion. Malformed Architecture JSON becomes a bounded failure instead
of leaving a generating job behind. Source hashes are checked again before
promotion so an output generated against changed files cannot replace the last
verified artifact. The accepted
files replace the subject's stable current artifact; the previous job becomes
`stale` and no historical HTML is retained. A ready artifact is served only from
`GET /api/refinements/<job-id>/artifact`. Filesystem paths supplied by a browser
are never accepted.

## Freshness and fallback

Status reads check the request's owned and included external source hashes.
Reindex also recomputes the dossier fingerprint with the request's context
policy and original critical-path extensions. Changes detected during generation
are recorded on the active job and rejected at acceptance without interrupting
its ownership. A changed or missing input marks a ready
job `stale`, stage `outdated`, with a reason and an explicitly labelled previous
artifact link. This does not delete the verified HTML. Failed regeneration keeps
that fallback; successful regeneration marks the previous job `replaced` and
withdraws its artifact URL. Reloading the browser graph clears cached refinement
statuses and discards in-flight responses from before the reload.
