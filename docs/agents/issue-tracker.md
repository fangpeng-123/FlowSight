# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/` and `docs/spec/`.

## Conventions

- One effort per directory: `.scratch/<effort-slug>/` (e.g. `.scratch/flowsight/`).
- **Decision tickets** (from `/wayfinder`): one file per ticket at `.scratch/<effort>/issues/<NN>-<slug>.md`, numbered from `01`. Carry `Type:` and `Status:` lines; blocking via a `Blocked by: NN, NN` line.
- **Build tickets** (from `/to-tickets`): one file per ticket at `.scratch/<effort>/tickets/<NN>-<slug>.md`, numbered from `01` in dependency order (blockers first) - never a single combined tickets file. Each has `**What to build:**`, `**Blocked by:**`, `**Status:**`, and acceptance-criteria checkboxes.
- **Specs** (from `/to-spec`): `docs/spec/<name>-spec.md` at the repo root.
- Triage state is recorded as a `Status:` line near the top of each file. Canonical statuses: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`; wayfinder decision tickets use `claimed` / `resolved` (optionally with a phase, e.g. `claimed (charting)`).
- Comments and conversation history append to the bottom of the file under a `## Comments` heading.

## When a skill says "publish to the issue tracker"

Create a new markdown file - under `.scratch/<effort>/` (`issues/` for decision tickets, `tickets/` for build tickets, creating the directory if needed) or under `docs/spec/` for a spec.

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per decision ticket.

- **Map**: `.scratch/<effort>/map.md` - the Destination / Notes / Decisions-so-far / Not-yet-specified / Out-of-scope body. Labelled `wayfinder:map` in its header.
- **Child decision ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer to the map's Decisions-so-far in `map.md`.
