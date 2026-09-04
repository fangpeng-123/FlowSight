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
  delivery-receipt.json
```

The dossier contains the selected subject, owned file scope and hashes,
internal graph facts, direct boundary facts, signatures, contracts, risks,
runtime evidence, locations, and origin tags. It contains no source text.

FlowSight commits `request.json` and `status.json` before emitting one compact
`refinement.requested` JSON line. The event contains only the event/job/subject/
project identifiers plus project-relative request and expected-result paths.
An Agent must scan existing pending jobs before relying on new events.

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
