# Module Deep-Read Refinement Protocol

FlowSight is the local request/status host. It does not start an Agent. The
Agent monitors newline-delimited JSON events and treats the filesystem job as
the source of truth.

## Browser API

- `POST /api/refinements` with `{"subject_id":"flowsight/server"}` creates or
  reuses a request and returns HTTP 202 with its current status.
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
  specification.json
  artifact.html
  reverse-id-map.json
  delivery-receipt.json
```

The dossier contains the selected subject, owned file scope and hashes,
internal graph facts, bounded cross-subject facts, signatures, contracts,
risks, runtime evidence, locations, and origin tags. It contains no source
text. Contract version 2 adds `source_scope.external_files`,
`relationships.external_context`, and the context policy/selection/overflow
summary; existing `nodes.boundary` and `relationships.boundary` remain the
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
the artifact cards.

## Result acceptance

The state path is `pending → claimed → generating → validating → ready`, with
`failed` and `cancelled` as explicit non-ready states. Diagnostics are bounded
to 1000 characters.

FlowSight registers a result only while the job is validating and only when the
result and delivery receipt match its job ID, subject ID, and input fingerprint;
the receipt reports success; and the specification, receipt, and HTML paths all
exist inside that job directory. A ready artifact is served only from
`GET /api/refinements/<job-id>/artifact`. Filesystem paths supplied by a browser
are never accepted.
