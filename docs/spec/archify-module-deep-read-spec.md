# FlowSight × Archify Module Deep-Read Spec

Status: **ready-for-agent** · Source: `/to-spec` synthesis of the FlowSight × Archify design discussion and completed `/grill-me` decision rounds.
Tracker idiom: FlowSight uses the local Markdown tracker. This spec is published under `docs/spec/` and registered in the FlowSight wayfinder map with the `ready-for-agent` status.

---

## Problem Statement

FlowSight already gives me a visual, interactive 3D overview of a Python project. That overview is useful for finding modules and understanding the project as a whole, but once I decide that one module deserves focused attention I still need a calmer, more deliberate explanation of that module's responsibility, entry points, core behavior, data movement, external dependencies, runtime evidence, and risks.

The global graph and a module deep read are different reading modes. Expanding more nodes inside the global graph does not automatically create a coherent explanation, and showing every function and edge at once recreates the overload that FlowSight is intended to avoid. I want to keep the project as the global reading subject, deliberately select one module as the current deep-reading subject, and move into a curated technical view without losing my place in the 3D overview.

Archify already turns a bounded technical description into a validated, self-contained, interactive architecture artifact. FlowSight already owns the stronger source facts: parser-derived structure, LLM-derived advisory annotations, and runtime-observed behavior. The missing capability is a reliable handoff between them. FlowSight must emit an on-demand module deep-read request; the Agent that launched and is monitoring FlowSight must consume that request, use Archify to generate a checked artifact, and return it for display inside FlowSight.

This integration must not make FlowSight responsible for starting or hosting an Agent. It must not silently invent module boundaries or topology, send the whole repository to an unspecified model, or treat an unvalidated HTML file as a successful result. It must also allow relevant code from other modules to appear as clearly marked external context, because understanding one module often requires following a call across folder boundaries.

## Solution

FlowSight adds an Agent-mediated **Module Deep Read** mode alongside its existing 3D project overview.

Before the interactive session begins, the Agent analyzes the project and publishes a stable **Reading Subject Catalog**. A reading subject is an Agent-identified functional module, normally rooted in a project folder with an explicit file membership. Parser-derived package and file structure remains intact; the catalog is an advisory reading layer over that structure rather than a replacement for it. Each source file has one primary reading-subject owner, while a module deep read may include relevant nodes from other subjects as external context.

Selecting a module in the 3D view remains a lightweight action. The module detail panel adds an explicit **Deep read this module** action. If a current validated artifact already exists, FlowSight can offer it immediately. Otherwise the action creates a durable, project-local refinement job and emits a machine-readable event on the server log. The Agent that launched and is monitoring FlowSight detects the event, claims the job, reads the bounded module dossier and permitted source context, authors one Archify Architecture specification, and runs Archify's validated delivery flow.

The browser stays in the 3D view while generation runs. It presents truthful states such as waiting for Agent, generating, validating, failed, stale, and ready. Completion never forces a navigation change; when the artifact is ready, the module panel offers **Open deep read**. Opening it replaces the main 3D canvas with the generated Archify artifact while retaining FlowSight-owned navigation. Returning restores the previous camera, expanded nodes, selected node, active graph view, and theme.

The Archify artifact is behavior-first rather than a decorative file tree. It explains the module's responsibility, entry points, core path, outputs, external dependencies, data/contracts, runtime evidence when available, and risks. Parser facts, LLM advice, and runtime observations remain visibly distinct. Related cross-module code may be shown to complete the explanation, but it appears inside an explicit external-context boundary with its owning reading subject identified.

Artifacts are generated only when requested. A successful result is cached against a content fingerprint. If any included source, graph input, generation contract, or Archify version changes, FlowSight marks the artifact stale. A replacement is written to staging and atomically overwrites the old artifact only after the new specification and final HTML pass the required Archify checks. Historical stale artifacts are not retained.

## User Stories

1. As a developer, I want the existing 3D project graph to remain my global overview, so that I can keep navigating the whole codebase visually.
2. As a developer, I want to choose one module as my current reading subject, so that I can move from exploration to focused understanding.
3. As a developer, I want module selection to remain separate from entering deep-read mode, so that an ordinary click does not start expensive generation.
4. As a developer, I want a clear **Deep read this module** action in the selected module's details, so that entering the focused mode is deliberate.
5. As a developer, I want FlowSight to reuse a current validated artifact when one exists, so that repeated reading is immediate.
6. As a developer, I want missing module deep reads to be generated only when requested, so that Agent and Archify work is not wasted on modules I never inspect.
7. As a developer, I want the Agent to identify functional reading subjects, so that FlowSight does not depend on a brittle hard-coded folder heuristic.
8. As a developer, I want reading subjects to normally be rooted in meaningful project folders, so that their identity remains understandable and stable.
9. As a developer, I want each reading subject to record its actual member files, so that its boundary is explicit rather than inferred from its label.
10. As a developer, I want the Agent to include or exclude individual files when a folder boundary is imperfect, so that the reading subject follows the code's function rather than a rigid directory rule.
11. As a developer, I want the parser-derived package and file graph to remain available, so that Agent-defined reading subjects do not replace structural facts.
12. As a developer, I want Agent-defined reading subjects to remain visibly advisory, so that I understand that the grouping is a reading judgment.
13. As a developer, I want every source file to have one primary reading-subject owner, so that containment, caching, and return navigation remain stable.
14. As a developer, I want a module deep read to include relevant functions or classes owned by another module, so that cross-module calls do not leave the explanation incomplete.
15. As a developer, I want cross-module nodes to be labelled with their owning reading subject, so that contextual inclusion is not mistaken for ownership.
16. As a developer, I want cross-module nodes to appear in a distinct external-context boundary, so that the selected module's true boundary stays obvious.
17. As a developer, I want external context to be bounded, so that a module deep read does not turn back into the whole-project graph.
18. As a developer, I want the Agent to follow a critical path beyond one hop when needed, so that a meaningful explanation is not cut off arbitrarily.
19. As a developer, I want excess external nodes to be summarized, so that the diagram remains readable when a module has many callers or dependencies.
20. As a developer, I want FlowSight to create a durable refinement job when I request a deep read, so that the request survives a missed log event or temporary Agent absence.
21. As a developer, I want the server to emit a structured event when a refinement job is created, so that the monitoring Agent can react without scraping prose logs.
22. As a developer, I want the Agent to recover pending jobs after it resumes monitoring, so that requests are not lost when the Agent is temporarily unavailable.
23. As a developer, I want FlowSight to say that it is waiting for the Agent when no job has been claimed, so that the UI does not make a false online claim.
24. As a developer, I want the Agent that launched FlowSight to remain the orchestration owner, so that FlowSight does not need an embedded Agent runtime.
25. As a developer, I want FlowSight to remain independent of a specific Agent vendor, so that future Agent integrations do not change the refinement job contract.
26. As a developer, I want the Agent to receive a bounded module dossier, so that it starts from FlowSight's known facts rather than rediscovering the whole project.
27. As a developer, I want the dossier to include module structure, signatures, relationships, contracts, risks, runtime statistics, divergence, and source locations when available, so that the Agent has enough evidence to author a useful deep read.
28. As a developer, I want the Agent to inspect the selected module and bounded external source context, so that it can verify how the critical behavior is implemented.
29. As a developer, I want parser-derived nodes and edges to remain authoritative, so that the Agent cannot create fictional structure for a cleaner story.
30. As a developer, I want runtime-observed relationships to remain authoritative observations, so that the deep read distinguishes what actually ran from what could run.
31. As a developer, I want Agent-inferred responsibilities, risks, and explanations marked as LLM-derived, so that advisory content never masquerades as parser truth.
32. As a developer, I want the Agent to curate the important nodes rather than display every function, so that the deep read has one understandable main story.
33. As a developer, I want entry points, central call paths, runtime-hit nodes, high-risk functions, and key data transformations prioritized, so that important behavior survives curation.
34. As a developer, I want omitted helper functions acknowledged as an aggregate, so that simplification is visible rather than deceptive.
35. As a developer, I want the first integration to produce one Archify Architecture artifact, so that the product validates one focused reading mode before adding more diagram types.
36. As a developer, I want the Architecture artifact to contain guided views for the module's important facets, so that I can move through responsibility, behavior, data, runtime, and risk without opening separate diagrams.
37. As a developer, I want empty or unsupported guided views omitted, so that a module without runtime evidence does not show a fake runtime story.
38. As a developer, I want code identifiers to remain exact while explanatory copy follows the reading language, so that the diagram is approachable without corrupting source names.
39. As a developer, I want external functions and classes represented by signatures and source locations rather than large code blocks, so that the Archify canvas remains a technical map rather than a code editor.
40. As a developer, I want Archify validation and delivery to complete before an artifact is offered, so that a present file is not confused with a trustworthy result.
41. As a developer, I want FlowSight to verify the Archify receipt, final artifact, and input fingerprint, so that an Agent's natural-language success claim is insufficient.
42. As a developer, I want the browser to remain usable while a deep read is generated, so that I can continue exploring the project.
43. As a developer, I want generation completion to produce an **Open deep read** action rather than force navigation, so that background work does not interrupt my current focus.
44. As a developer, I want a generation job to continue if I select another module, so that completed work can be cached rather than discarded.
45. As a developer, I want at most one active generation job in the first version, so that Agent and filesystem work remain predictable.
46. As a developer, I want duplicate requests for the same module fingerprint deduplicated, so that repeated clicks do not start duplicate Agent work.
47. As a developer, I want queued jobs to be cancellable before they are claimed, so that accidental requests do not consume Agent work.
48. As a developer, I want failed generation for one module to leave the 3D overview and other module artifacts working, so that refinement failure is isolated.
49. As a developer, I want actionable failure status and a retry action, so that I can recover without restarting FlowSight.
50. As a developer, I want opening a ready artifact to replace the main graph canvas, so that the deep read has enough space to be legible.
51. As a developer, I want a visible project-to-module breadcrumb and return action, so that I always know which reading level I am in.
52. As a developer, I want returning from a deep read to restore the 3D camera, expanded nodes, selection, active view, and theme, so that I do not lose my exploration context.
53. As a developer, I want an artifact to become stale when any source actually included in it changes, so that cross-module context cannot silently become outdated.
54. As a developer, I want graph schema, generation-contract, and Archify version changes to invalidate incompatible artifacts, so that cache reuse remains truthful.
55. As a developer, I want stale status displayed clearly, so that an old explanation is never presented as current.
56. As a developer, I want a newly generated artifact to replace the stale file only after successful validation, so that failed regeneration cannot destroy the last usable result.
57. As a developer, I want the successful replacement to overwrite the previous artifact instead of retaining history, so that the local FlowSight workspace does not accumulate obsolete diagrams.
58. As a developer, I want the final deep read to answer the module's responsibility, entry points, main path, outputs, dependencies, and risks without requiring source reading, so that the feature delivers focused understanding rather than merely rendering a graph.
59. As a developer, I want every displayed topology relationship to trace back to parser or runtime evidence, so that the visual explanation remains trustworthy.
60. As a developer, I want the integration to remain local and single-user, so that it preserves FlowSight's personal-tool boundary.

## Implementation Decisions

### Product boundary and ownership

- The existing 3D graph remains the project-level overview and fixed entry point. This effort does not reconsider whether that view should exist.
- FlowSight owns project facts, reading-subject selection, durable refinement jobs, status presentation, artifact hosting, and navigation state.
- The external Agent owns reading-subject discovery, job consumption, bounded source inspection, Archify authorship, and repair attempts.
- Archify owns its typed Architecture specification, validation, deterministic delivery, final self-contained HTML, and delivery receipt.
- FlowSight does not start, embed, authenticate, or host an Agent in this version. The same Agent session that launches FlowSight is expected to monitor its server output and process pending refinement work.
- The integration boundary is filesystem plus machine-readable server events, not an Agent-vendor SDK.

### Reading Subject Catalog

- Add a project-local Reading Subject Catalog generated by the Agent before interactive use.
- A reading subject is an advisory functional grouping layered over the parser graph. It does not replace parser-derived package, file, class, function, or relationship facts.
- Each subject has a stable identifier, user-facing label, root folder, explicit member files, optional exclusions, rationale, and an optional manual lock.
- Stable identity is based on the subject's project-relative root rather than its Agent-generated label.
- Each source file has at most one primary subject owner. Catalog validation rejects duplicate primary ownership, missing files, paths outside the project, duplicate subject IDs, and roots excluded by project policy.
- Human corrections may lock a subject. Later Agent discovery must preserve locked subjects and may update only unlocked entries.
- Cross-module display is not secondary ownership. The generated artifact records the owning subject for every contextual node.

### Bounded module dossier

- The server builds a deterministic dossier for the selected subject from the current GraphDocument, Reading Subject Catalog, enrichment data, optional runtime overlay, and source locations.
- The dossier includes the selected subject's members and the relationships that cross its boundary. It preserves every node and edge origin tag.
- The Agent may inspect source files owned by the subject and the bounded external files required to explain selected cross-boundary behavior.
- External context begins with direct callers and callees. The Agent may continue along a critical path when a one-hop view would be incomplete.
- Default curation budgets are 8–18 internal primary nodes, no more than two external reading subjects, and no more than six external primary nodes. Overflow is represented by truthful aggregates.
- The diagram is behavior-first. Directory and file structure are supporting evidence, while responsibility, entry points, core path, data movement, external dependencies, runtime evidence, and risk form the main reading sequence.

### Refinement job contract

- Add a durable project-local refinement job store. Each job has a unique ID and a directory containing an immutable request, mutable status, staged outputs, final result metadata, Archify source, final artifact, and delivery receipt.
- Creating a request is idempotent for the same subject ID and input fingerprint. An existing pending, active, or ready job is returned instead of creating a duplicate.
- The job state machine is `pending → claimed → generating → validating → ready`, with `failed`, `cancelled`, and `stale` as explicit non-ready states.
- Only a pending job may be cancelled by the browser. A claimed job continues even if the user changes selection or leaves the module.
- The first version permits one claimed or actively generating job at a time. Additional requests remain pending in creation order.
- Claiming must be atomic so that a repeated event or recovering Agent cannot process the same job twice.
- The server writes the durable request before emitting a notification. The durable job is the source of truth; the log event is only a wake-up hint.
- The server emits one newline-delimited JSON event for a newly pending job. The event identifies the event type, job ID, subject ID, request location, project identity, and expected result location without embedding source code or natural-language instructions.
- An Agent beginning or resuming monitoring scans pending jobs before waiting for new events, allowing recovery from missed notifications.
- The server does not claim that an Agent is online without a separate heartbeat contract. In this version, an unclaimed request remains in a truthful **Waiting for Agent** state.

### Local HTTP interface

- Add a request endpoint that accepts a reading-subject ID, validates that the subject exists, snapshots the current dossier and fingerprint, creates or reuses a job, and returns HTTP 202 with the job identity and status.
- Add a status endpoint that returns the current state, timestamps, current stage, stale reason, validated artifact availability, and a bounded failure diagnostic.
- Add a cancellation endpoint limited to pending jobs.
- Add a same-origin artifact endpoint that serves only the verified artifact registered for the requested job or subject. It must not accept arbitrary filesystem paths.
- Existing graph, enrichment, divergence, and reindex endpoints remain compatible.
- Reindexing refreshes subject and artifact freshness without deleting the current verified artifact before a replacement is available.

### Agent processing contract

- The Agent reads the immutable request and may enrich its understanding only within the request's source scope and bounded critical-path allowance.
- The Agent creates one Archify Architecture specification. Other Archify diagram types are not selected automatically in this version.
- Topology in the Architecture specification must be derived from parser or runtime evidence in the dossier. The Agent may omit, aggregate, label, arrange, and explain evidence but may not invent topology.
- LLM-derived purpose, contract, risk, grouping rationale, and narrative are permitted only when visibly represented as advisory rather than authoritative structure.
- The Agent should prefer key entry points, central call paths, runtime-hit nodes, high-risk functions, and important transformations. It records the count and category of omitted helper nodes.
- The Architecture may use up to five curated guided views. Empty facets are omitted. A runtime-focused view is included only when runtime evidence exists.
- Internal components and external-context components are separated by explicit labelled boundaries. External nodes retain their owning reading-subject identity.
- FlowSight identifiers are mapped deterministically to Archify-safe stable IDs. A reverse mapping is retained with the result for traceability and future interaction, but node-level return navigation is not implemented in this version.
- Parser, LLM, and runtime meaning are visually distinct. Runtime highlighting is used only for observed behavior; absence of trace data never creates simulated runtime flow.
- The Agent follows Archify's focused repair limit. After bounded repair attempts, it records a failed result rather than looping indefinitely or returning an unchecked artifact.

### Result acceptance and artifact replacement

- The Agent renders into a staging location and atomically writes final result metadata only after Archify delivery succeeds.
- A result is ready only when the Archify command succeeds, the machine-readable delivery receipt reports success, the final HTML exists, and the specification/result fingerprints match the request.
- The server independently validates result metadata and constrains every reported path to the job or artifact storage area before exposing it.
- Natural-language Agent output, HTML existence alone, or a browser's ability to open the file is not sufficient evidence of success.
- A failed job preserves the previous verified artifact and records a bounded diagnostic suitable for display and retry.
- Once a replacement has passed validation, it atomically overwrites the module's previous artifact. No historical artifact archive is retained.

### Freshness and fingerprinting

- Subject request fingerprints cover the subject definition, owned source contents, relevant GraphDocument facts, enrichment/runtime inputs included in the dossier, and the dossier contract version.
- Final artifact fingerprints additionally cover every external source file actually used, the Agent generation-contract version, the Archify specification bytes, and the Archify version reported by the receipt.
- FlowSight recomputes freshness from the result's exact input manifest. A change to any included internal or cross-module source marks the artifact stale.
- A stale artifact remains identifiable but is not presented as current. Requesting regeneration creates or reuses a job for the new fingerprint.
- Successful regeneration replaces the stale artifact. The former file is not retained as history.

### Browser interaction

- Selecting a module continues to perform the current selection and detail-panel behavior.
- Only reading-subject-backed module nodes expose the deep-read action.
- A ready current artifact exposes **Open deep read** immediately. A missing or stale artifact exposes generation or regeneration. Active jobs expose their truthful stage; failed jobs expose retry.
- The browser polls bounded job status while a request is active. It does not assume completion from elapsed time or a file URL.
- Completion never auto-navigates. The user deliberately opens the ready artifact.
- The deep-read mode replaces the main 3D canvas but remains inside the FlowSight page shell. FlowSight owns the breadcrumb, status, and return control; the Archify artifact is loaded as a contained same-origin document.
- Entering deep-read mode snapshots camera position, graph expansion state, selected node, active graph dimension, theme, and relevant panel state.
- Returning restores that snapshot without rebuilding or reorienting the graph.
- The first version displays external functions/classes as diagram nodes with signatures and source locations. It does not embed large source-code excerpts or implement per-node source navigation.

### Safety and privacy

- Job and result paths are project-local and normalized before use. Arbitrary absolute paths, parent traversal, URL paths, and output destinations outside the approved refinement area are rejected.
- Source code is never embedded in the structured notification log.
- This version relies on the already-running Agent's own model/provider authorization. Direct model-provider configuration and API-key handling are not part of FlowSight.
- Future direct provider integration must expose provider, model, and source scope before transmitting code, but that future contract does not block this Agent-mediated version.

## Testing Decisions

### Primary seam

- The primary automated seam is the complete refinement protocol from a module request at the local HTTP boundary to a verified artifact becoming available at the browser boundary.
- A deterministic fixture Agent/Archify producer handles the job in tests. The test starts from the existing fixture Python project and a fixture Reading Subject Catalog, submits a module request, observes the durable request and structured event, claims the job, supplies staged Archify source/receipt/artifact fixtures, completes the result atomically, polls ready status, and retrieves the verified artifact.
- This seam asserts public behavior: IDs, state transitions, durability, deduplication, receipt acceptance, freshness, artifact availability, and failure isolation. It does not assert internal helper calls or exact filesystem implementation beyond the published job contract.
- Real LLM quality is never asserted. The fixture content is deterministic, and tests verify provenance, attachment, curation bounds, and handoff plumbing rather than prose quality.

### Contract and module tests

- Reading Subject Catalog tests cover stable IDs, explicit membership, manual locks, missing/out-of-project files, duplicate subject IDs, duplicate primary ownership, and valid cross-module references.
- Dossier tests cover preservation of parser/LLM/runtime origins, selected-subject membership, incoming/outgoing boundary relationships, bounded critical-path context, and truthful overflow aggregation.
- Job-store tests cover atomic creation, duplicate request reuse, one-active-job enforcement, ordered pending work, atomic claiming, pending cancellation, recovery after missed events, and bounded failure diagnostics.
- Result-validation tests reject missing or failed receipts, missing artifacts, mismatched job/subject/fingerprint data, path escape, partial writes, and natural-language-only completion claims.
- Freshness tests change an owned file, an actually included external file, an unused external file, graph input, contract version, and Archify version independently. Only inputs in the published fingerprint invalidate the artifact.
- Replacement tests verify that the old artifact remains available while a replacement is staged or fails, that a successful replacement atomically overwrites it, and that no historical artifact is retained.
- Frontend adapter/state tests cover action availability, pending/generating/validating/ready/failed/stale presentation, no automatic navigation on completion, deep-read entry, and exact restoration of the prior 3D state.
- Artifact serving tests verify same-origin retrieval of only a registered verified output and rejection of arbitrary path requests.

### Manual acceptance

- Use FlowSight's runtime-overlay module as the first real acceptance subject.
- Start FlowSight through an Agent that continues monitoring for refinement events.
- Request the runtime-overlay module from the browser and verify the Agent receives and claims the durable job.
- Verify Archify produces a checked Architecture artifact that clearly separates internal runtime-overlay code from any referenced skeleton or server context.
- Without opening source files, confirm that the artifact explains the module's responsibility, entry points, trace correlation path, GraphDocument mutation, external dependencies, runtime evidence, and important risks.
- Return to the 3D view and confirm camera, expansion, selection, active dimension, and theme are restored.
- Change one source file included in the artifact, confirm stale status, regenerate, and confirm the new validated artifact overwrites the old one without keeping history.
- Stop Agent monitoring, submit another request, and confirm the request persists as waiting rather than disappearing or claiming false progress.

### Prior art

- The existing pipeline test establishes the repository's preferred highest seam: a fixture project enters and a complete graph document exits, with external behavior and provenance asserted rather than parser internals.
- The existing runtime-overlay tests use a checked-in trace fixture to verify deterministic correlation and actual-on-expected behavior without requiring the optional runtime tracer.
- The existing JavaScript adapter tests exercise pure graph-to-render-state behavior without asserting renderer pixels. Deep-read navigation and status presentation should follow the same pure-state approach where possible.
- Existing enrichment tests stub nondeterministic LLM behavior and assert attachment, caching, and invalidation rather than generated prose. Agent-mediated deep-read tests follow the same principle.

## Out of Scope

- Reconsidering, removing, or replacing the existing 3D project overview.
- Pre-generating Archify artifacts for every module.
- FlowSight directly starting or embedding an Agent runtime.
- Direct LLM provider calls from FlowSight.
- API-key storage, provider selection, model selection, or a general multi-provider abstraction.
- A general prompt-authoring, prompt-versioning, or orchestration-chain product.
- Non-Python repositories.
- Treating files, classes, or functions as independent deep-reading subjects.
- Archify Sequence, Data Flow, Workflow, Lifecycle, or Architecture Delta generation.
- Generating multiple Archify diagram types and automatically choosing among them.
- Bidirectional live selection synchronization between FlowSight and the Archify document.
- Clicking an Archify node to select an exact FlowSight node or open an exact source snippet.
- Embedding large source-code blocks in the Archify artifact.
- Allowing more than one Agent to claim or process jobs concurrently.
- Cloud-hosted artifacts, remote sharing, authentication, multi-user collaboration, or permissions management.
- Retaining a history of stale or replaced module artifacts.
- Allowing Agent-created topology without parser or runtime evidence.
- A general-purpose folder-classification rule intended to replace Agent-defined reading subjects.

## Further Notes

- The core product transition is **project overview → selected reading subject → validated module deep read → restored project overview**.
- “Module” in the user experience means an Agent-defined Reading Subject. It is intentionally distinct from the parser's Python package node, even when both refer to the same folder.
- “External context” means code displayed to explain the selected subject while retaining its original primary ownership. It does not mean third-party code exclusively.
- The durable job is authoritative; the structured server event only reduces response latency.
- The current artifact filename is stable per reading subject. Regeneration uses staging plus atomic replacement so “overwrite stale files” never means deleting the last usable artifact before a valid replacement exists.
- The feature succeeds when the user can explain the selected module's responsibility, entry points, core path, outputs, dependencies, runtime evidence, and risks without reading source, while every topology relationship remains traceable to parser or runtime evidence.
